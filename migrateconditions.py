import os
import sys
import argparse
import configparser
import library.localstore as store
import library.clients.alertsclient as ac
import library.migrationlogger as logger
import library.utils as utils
import library.status.conditionstatus as cs
import library.migrator.loc_failure_conditions as lfc_migrator
import library.migrator.synth_conditions as sc_migrator
import library.migrator.app_conditions as ac_migrator
import library.migrator.nrql_conditions as nrql_migrator
import library.migrator.extsvc_conditions as extsvc_migrator
import library.migrator.infra_conditions as infra_migrator
from typing import List

logger = logger.get_logger(os.path.basename(__file__))
SYNTHETICS = 'synthetics'
APP_CONDITIONS = 'app-conditions'
NRQL_CONDITIONS = 'nrql-conditions'
EXT_SVC_CONDITIONS = 'ext-svc-conditions'
INFRA_CONDITIONS = 'infra-conditions'
ALL_CONDITIONS = [SYNTHETICS, APP_CONDITIONS, NRQL_CONDITIONS, EXT_SVC_CONDITIONS, INFRA_CONDITIONS]  # currently used only for testing

def create_argument_parser():
    parser = argparse.ArgumentParser(description='Migrate Alert Conditions from source to target policy')
    parser.add_argument('--fromFile', nargs=1, type=str, required=False, help='Path to file with alert policy names')
    parser.add_argument('--fromFileEntities', nargs=1, type=str, required=False, help='Path to file with entity IDs')
    parser.add_argument('--sourceAccount', nargs=1, type=str, required=True, help='Source accountId')
    parser.add_argument('--sourceApiKey', nargs=1, type=str, required=True, help='Source account API Key or \
                                                                        set environment variable ENV_SOURCE_API_KEY')
    parser.add_argument('--targetAccount', nargs=1, type=str,  required=True, help='Target accountId')
    parser.add_argument('--targetApiKey', nargs=1, type=str, required=False, help='Target API Key, \
                                                                        or set environment variable ENV_TARGET_API_KEY')
    parser.add_argument('--matchSourceState', dest='matchSourceState', required=False, action='store_true',
                    help='Pass --matchSourceState to match condition enable/disable state from source account instead of disabling in target account')
    parser.add_argument('--synthetics', dest='synthetics', required=False, action='store_true',
                    help='Pass --synthetics to migrate synthetics conditions')
    parser.add_argument('--app_conditions', dest='app_conditions', required=False, action='store_true',
                        help='Pass --app_conditions to migrate app conditions')
    parser.add_argument('--nrql_conditions', dest='nrql_conditions', required=False, action='store_true',
                        help='Pass --nrql_conditions to migrate NRQL conditions')
    parser.add_argument('--ext_svc_conditions', dest='ext_svc_conditions', required=False, action='store_true',
                        help='Pass --ext_svc_conditions to migrate external service conditions')
    parser.add_argument('--infra_conditions', dest='infra_conditions', required=False, action='store_true',
                        help='Pass --infra_conditions to migrate infrastructure conditions')
    parser.add_argument('--useLocal', dest='useLocal', required=False, action='store_true',
                        help='By default the policy to entity map is fetched. Pass this to use the policy to entity map pre-fetched by store_policy_entity_map.')
    return parser

def print_args(src_api_key, tgt_api_key):
    if (args.fromFile):
        logger.info("Using fromFile : " + args.fromFile[0])
    if (args.fromFileEntities):
        logger.info("Using fromFileEntities : " + args.fromFileEntities[0])
    logger.info("Using sourceAccount : " + args.sourceAccount[0])
    logger.info("Using sourceApiKey : " + len(src_api_key[:-4])*"*"+src_api_key[-4:])
    logger.info("Using targetAccount : " + args.targetAccount[0])
    logger.info("Using targetApiKey : " + len(tgt_api_key[:-4]) * "*" + tgt_api_key[-4:])
    if args.matchSourceState:
        logger.info("Matching condition enable/disable state in target account instead of disabling all new conditions")
    if args.synthetics:
        logger.info("Migrating conditions of type " + SYNTHETICS)
    if args.app_conditions:
        logger.info("Migrating conditions of type " + APP_CONDITIONS)
    if args.nrql_conditions:
        logger.info("Migrating conditions of type " + NRQL_CONDITIONS)
    if args.ext_svc_conditions:
        logger.info("Migrating conditions of type " + EXT_SVC_CONDITIONS)
    if args.infra_conditions:
        logger.info("Migrating conditions of type " + INFRA_CONDITIONS)

def migrate_conditions(policy_names, src_account_id, src_api_key, tgt_account_id, tgt_api_key, cond_types, match_source_status):
    all_alert_status = {}
    for policy_name in policy_names:
        logger.info('Migrating conditions for policy ' + policy_name)
        all_alert_status[policy_name] = {}
        src_result = ac.get_policy(src_api_key, policy_name)
        if not src_result['policyFound']:
            logger.error("Skipping as policy not found in source account " + policy_name)
            all_alert_status[policy_name][cs.ERROR] = 'Policy not found in source account'
            continue
        src_policy = src_result['policy']
        tgt_result = ac.get_policy(tgt_api_key, policy_name)
        if not tgt_result['policyFound']:
            logger.error("Skipping as policy not found in target account " + policy_name)
            all_alert_status[policy_name][cs.ERROR] = 'Policy not found in target account'
            continue
        tgt_policy = tgt_result['policy']
        if SYNTHETICS in cond_types:
            sc_migrator.migrate(all_alert_status, policy_name, src_api_key, src_policy,
                                tgt_account_id, tgt_api_key, tgt_policy, match_source_status)
            lfc_migrator.migrate(all_alert_status, policy_name, src_api_key, src_policy,
                                 tgt_account_id, tgt_api_key, tgt_policy, match_source_status)
        if APP_CONDITIONS in cond_types:
            ac_migrator.migrate(all_alert_status, policy_name, src_api_key, src_policy, tgt_account_id,
                                tgt_api_key, tgt_policy, match_source_status)
        if NRQL_CONDITIONS in cond_types:
            nrql_migrator.migrate(all_alert_status, policy_name, src_api_key, src_policy, tgt_account_id,
                                tgt_api_key, tgt_policy, match_source_status)
        if EXT_SVC_CONDITIONS in cond_types:
            extsvc_migrator.migrate(all_alert_status, policy_name, src_api_key, src_policy, tgt_account_id,
                                  tgt_api_key, tgt_policy, match_source_status)
        if INFRA_CONDITIONS in cond_types:
            infra_migrator.migrate(all_alert_status, policy_name, src_api_key, src_policy, tgt_account_id, 
                                tgt_api_key, tgt_policy, match_source_status)
    return all_alert_status

def parse_condition_types(args):
    condition_types = []
    if args.synthetics:
        condition_types.append(SYNTHETICS)
    if args.app_conditions:
        condition_types.append(APP_CONDITIONS)
    if args.nrql_conditions:
        condition_types.append(NRQL_CONDITIONS)
    if args.ext_svc_conditions:
        condition_types.append(EXT_SVC_CONDITIONS)
    if args.infra_conditions:
        condition_types.append(INFRA_CONDITIONS)
    return condition_types

def migrate(
    policy_file_path: str,
    entity_file_path: str,
    source_acct_id: int,
    target_acct_id: int,
    source_api_key: str,
    target_api_key: str,
    cond_types: List[str],
    use_local: bool = False,
    match_source_state: bool = False,
):
    policy_names = utils.load_alert_policy_names(
        policy_file_path,
        entity_file_path,
        source_acct_id,
        source_api_key,
        use_local
    )

    status = migrate_conditions(
        policy_names,
        source_acct_id,
        source_api_key,
        target_acct_id,
        target_api_key,
        cond_types,
        match_source_state
    )

    status_file = ac.get_alert_status_file_name(
        policy_file_path,
        entity_file_path,
        source_acct_id,
        target_acct_id
    )
    store.save_status_csv(status_file, status, cs)

    return status_file

class MigrateConditionsCommand:
    def configure_parser(self, migrate_subparsers, global_options_parser):
        # Create the parser for the "conditions" command
        policies_parser = migrate_subparsers.add_parser('conditions', help='policies help', parents=[global_options_parser])
        policies_parser.add_argument(
            '--policy_file',
            nargs=1,
            type=str,
            required=False,
            help='Path to file with alert policy names'
        )
        policies_parser.add_argument(
            '--entity_file',
            nargs=1,
            type=str,
            required=False,
            help='Path to file with entity names and IDs'
        )
        policies_parser.add_argument(
            '--use_local',
            dest='use_local',
            required=False,
            action='store_true',
            help='By default the policy to entity map is fetched. Pass this to use the policy to entity map pre-fetched by store_policy_entity_map.'
        )
        policies_parser.add_argument(
            '--match_source_state',
            dest='match_source_state',
            required=False,
            action='store_true',
            help='Pass --match_source_state to match condition enable/disable state from source account instead of disabling in target account'
        )
        policies_parser.set_defaults(func=self.run)

    def run(self, config: configparser.ConfigParser, args: argparse.Namespace):
        base_config = utils.process_base_config(config, 'migrate.conditions')

        policy_file_path = config.get(
            'migrate.conditions',
            'policy_file',
            fallback = args.policy_file
        )        
        entity_file_path = config.get(
            'migrate.conditions',
            'entity_file',
            fallback = args.entity_file
        )
        if not policy_file_path and not entity_file_path:
            utils.error_message_and_exit(
                'Error: Either a policy file or entity file must be specified.'
            )

        use_local = config.getboolean(
            'migrate.conditions',
            'use_local',
            fallback = args.use_local
        )
        match_source_state = config.getboolean(
            'migrate.conditions',
            'match_source_state',
            fallback = args.match_source_state
        )

        migrate(
            policy_file_path,
            entity_file_path,
            base_config['source_account_id'],
            base_config['target_account_id'],
            base_config['source_api_key'],
            base_config['target_api_key'],
            cond_types,
            use_local,
            match_source_state
        )
        
if __name__ == '__main__':
    parser = create_argument_parser()

    args = parser.parse_args()

    source_api_key = utils.ensure_source_api_key(args)
    if not source_api_key:
        utils.error_and_exit('source_api_key', 'ENV_SOURCE_API_KEY')

    target_api_key = utils.ensure_target_api_key(args)
    if not target_api_key:
        utils.error_and_exit('target_api_key', 'ENV_TARGET_API_KEY')
    
    cond_types = parse_condition_types(args)
    if len(cond_types) == 0:
        logger.error('At least one condition type must be specified currently supported ' +
                     SYNTHETICS + ',' + APP_CONDITIONS + ',' + NRQL_CONDITIONS + ',' + INFRA_CONDITIONS)
        sys.exit()

    print_args(source_api_key, target_api_key)

    logger.info('Starting Alert Conditions Migration')

    fromFile = args.fromFile[0] if 'fromFile' in args else None
    fromFileEntities = args.fromFileEntities[0] if 'fromFileEntities' in args else None
    if not fromFile and not fromFileEntities:
        logger.error('Error: At least one of fromFile or fromFileEntities must be specified.')
        sys.exit()

    source_acct_id = args.sourceAccount[0]
    target_acct_id = args.targetAccount[0]

    print_args(source_api_key, target_api_key)

    migrate(
        fromFile,
        fromFileEntities,
        source_acct_id,
        target_acct_id,
        source_api_key,
        target_api_key,
        cond_types,
        args.useLocal,
        args.matchSourceState
    )

    logger.info('Done Alert Conditions Migration')