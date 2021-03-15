from aiohttp import ClientSession
from asyncio import gather, get_event_loop
from functools import reduce
import logging
from io import StringIO
from json import dumps as json_dumps
import pandas as pd
from os import path
import time

import aligners
from config import config
from mongo import retrieve_file, retrieve_alignment_result, insert_alignment, insert_comparison
from server_queue import app
from scores import compute_scores, split_score_data_as_tsvs
from ppi_sources.isobase.local import isobase_local_source
from ppi_sources.stringdb.api import stringdb_api_source
from ppi_sources.stringdbvirus.local import stringdbvirus_local_source
from util import all_equal, write_tsv_to_string
from aligners import load_aligner_classes

logger = logging.getLogger(__name__)


ALIGNERS_DISPATCHER = load_aligner_classes('aligners.json')


def connect_to_db(db_name):
    if db_name == 'isobase':
        return isobase_local_source('/opt/local-db/isobase')
    elif db_name == 'stringdb':
        return stringdb_api_source(config['SOURCES_API_URL'])
    elif db_name == 'stringdbvirus':
        return stringdbvirus_local_source('/opt/local-db/stringdb-virus-gv')
    else:
        raise ValueError(f'database not supported: {db_name}')


async def db_get_network(db, net_desc):
    if net_desc.get('edges', None) is None:
        return await db.get_network(net_desc)
    else:
        return await db.build_custom_network(net_desc)


def networks_summary(db_name, net1_desc, net1, net2_desc, net2):
    return {
        'db': db_name,

        'net1': net1_desc,
        'net1_details': net1.get_details() if net1 is not None else {},

        'net2': net2_desc,
        'net2_details': net2.get_details() if net2 is not None else {},
    }


def alignment_summary(net1, net2, alignment, bitscore_matrix, ontology_mapping, files):
    scores = compute_scores(net1, net2, alignment, bitscore_matrix, ontology_mapping)
    files.update(split_score_data_as_tsvs(scores))

    return scores


async def process_alignment(job_id, data):
    db_name = data['db']
    net1_desc = data['net1']
    net2_desc = data['net2']
    aligner_name = data['aligner'].lower()
    aligner_params = data.get('aligner_params', dict())

    net1 = None
    net2 = None

    try:
        async with connect_to_db(db_name.lower()) as db:
            logger.info(f'[{job_id}] fetching networks')
            net1 = await db_get_network(db, net1_desc)
            net2 = await db_get_network(db, net2_desc)

            logger.info(f'[{job_id}] fetching bitscore matrices')
            net1_net2_scores = await db.get_bitscore_matrix(net1, net2)

            if aligner_name == 'alignet':
                net1_scores = await db.get_bitscore_matrix(net1, net1)
                net2_scores = await db.get_bitscore_matrix(net2, net2)
                run_args = (net1, net2, net1_scores, net2_scores, net1_net2_scores)
            else:
                run_args = (net1, net2, net1_net2_scores)

            logger.info(f'[{job_id}] retrieving GO annotations')
            ontology_mapping = await db.get_ontology_mapping([net1, net2])

    except Exception as e:
        logger.exception(f'[{job_id}] exception was raised fetching required data')
        results = {'ok': False, 'exception': str(e)}

    else:
        try:
            if aligner_name not in ALIGNERS_DISPATCHER:
                raise LookupError(f'aligner not supported: {aligner_name}')

            aligner = ALIGNERS_DISPATCHER[aligner_name](**aligner_params)

            results = aligner.run(
                *run_args,
                run_dir_base_path='/opt/running-alignments',
                template_dir_base_path='/opt/aligner-templates')

            results['exception'] = None

        except Exception as e:
            logger.exception(f'[{job_id}] exception was raised running alignment')
            results = {'ok': False, 'exception': str(e)}

    response_data = {
        'aligner': aligner_name,
        'aligner_params': aligner_params,
        'results': results,
        'timestamp': time.time(),
    }
    response_data.update(networks_summary(db_name, net1_desc, net1, net2_desc, net2))

    result_files = dict()

    if 'alignment' in results:
        alignment = results['alignment']
        results['alignment'] = {'file': 'alignment_tsv'}

        result_files['alignment_tsv'] = write_tsv_to_string(alignment.reset_index())

        logger.info(f'[{job_id}] computing scores')

        try:
            response_data['scores'] = alignment_summary(net1, net2, alignment, net1_net2_scores, ontology_mapping, result_files)
        except:
            logger.exception(f'[{job_id}] exception was raised while computing scores')

    return response_data, result_files


async def process_alignment_and_send(data):
    job_id = data['job_id']

    try:
        logger.info(f'[{job_id}] processing alignment {data}')

        response_data, result_files = await process_alignment(job_id, data)

    except Exception as e:
        logger.exception(f'[{job_id}] exception was raised while processing alignment')

        response_data = {
            'results': {'ok': False, 'exception': str(e)}
        }
        result_files = dict()

    logger.debug(f'[{job_id}] alignment finished with result: {response_data}')
    result_id = await insert_alignment(job_id, response_data, result_files)
    logger.info(f'[{job_id}] inserted result as {result_id}')

    await send_finished_alignment(job_id, result_id)


@app.task(name='process_alignment', queue='server_aligner')
def process_alignment_sync(data):
    loop = get_event_loop()
    return loop.run_until_complete(process_alignment_and_send(data))


async def fetch_and_validate_previous_results(job_id, result_ids):
    logger.info(f'[{job_id}] validating previous results {result_ids}')

    if len(result_ids) == 0:
        raise ValueError(f'[{job_id}] no previous results')

    records = await gather(*[retrieve_alignment_result(result_id) for result_id in result_ids])
    records = [record for record in records if record['results']['ok'] and 'alignment_tsv' in record['files']]

    if len(records) == 0:
        raise ValueError(f'[{job_id}] no successful alignments to compare')

    db_names = [record['db'].lower() for record in records]
    if not all_equal(db_names):
        raise ValueError(f'[{job_id}] mismatching databases: ' + str(db_names))

    net1_descs = [record['net1'] for record in records]
    if not all_equal(net1_descs):
        raise ValueError(f'[{job_id}] mismatching input networks: ' + str(net1_descs))

    net2_descs = [record['net2'] for record in records]
    if not all_equal(net2_descs):
        raise ValueError(f'[{job_id}] mismatching output networks: ' + str(net2_descs))

    aligners = [record['aligner'] for record in records]

    if len(aligners) != len(set(aligners)):
        raise ValueError(f'[{job_id}] repeated aligners: ' + str(aligners))

    alignments = await gather(*[retrieve_file(record['files']['alignment_tsv']) for record in records])
    alignments = [StringIO(alignment.decode('utf-8')) for alignment in alignments]
    alignments = [pd.read_csv(alignment, sep='\t', index_col=0) for alignment in alignments]

    alignment_headers = [alignment.index.names + alignment.columns.values.tolist() for alignment in alignments]

    if not all_equal(alignment_headers):
        raise ValueError(f'[{job_id}] mismatching alignment headers: ' + str(alignment_headers))

    for aligner, alignment in zip(aligners, alignments):
        alignment.rename(inplace=True, columns=lambda col: f'{col}_{aligner}')

    joined = alignments[0].join(alignments[1:], how='outer').rename_axis(index=alignments[0].index.name)

    return db_names[0], net1_descs[0], net2_descs[0], records, alignment_headers[0], joined


async def compare_alignments(job_id, data):
    logger.info(f'[{job_id}] comparing alignments {data}')

    results = {'ok': True, 'exception': None}
    result_files = dict()

    result_ids = data.get('results_object_ids', [])

    response_data = {'results': results, 'results_object_ids': result_ids}

    try:
        db_name, net1_desc, net2_desc, records, alignment_header, joined = \
                await fetch_and_validate_previous_results(job_id, result_ids)

        logger.info(f'[{job_id}] fetching input data')

        async with connect_to_db(db_name) as db:
            net1 = await db_get_network(db, net1_desc)
            net2 = await db_get_network(db, net2_desc)
            bitscore_matrix = await db.get_bitscore_matrix(net1, net2)
            ontology_mapping = await db.get_ontology_mapping([net1, net2])

    except Exception as e:
        logger.exception(f'[{job_id}] exception was raised fetching required data')
        results.update({'ok': False, 'exception': str(e)})

    else:
        consensus = joined.loc[joined.agg(all_equal, axis=1)].iloc[:,:1]
        consensus.columns = [alignment_header[1]]
        consensus.rename_axis(index=alignment_header[0], inplace=True)

        results.update({
            'joined': {'file': 'joined_tsv'},
            'consensus': {'file': 'consensus_tsv'}
        })

        result_files.update({
            'joined_tsv': write_tsv_to_string(joined.reset_index()),
            'consensus_tsv': write_tsv_to_string(consensus.reset_index())
        })

        response_data.update(networks_summary(db_name, net1_desc, net1, net2_desc, net2))

        logger.info(f'[{job_id}] computing scores')

        try:
            response_data['consensus_scores'] = alignment_summary(net1, net2, consensus, bitscore_matrix, ontology_mapping, result_files)
        except:
            logger.exception(f'[{job_id}] exception was raised while computing scores')

        response_data['aligners'] = [
            {'aligner': record['aligner'], 'aligner_params': record['aligner_params']}
            for record in records
        ]

    return response_data, result_files



async def compare_alignments_and_send(data):
    job_id = data['job_id']

    try:
        response_data, result_files = await compare_alignments(job_id, data)

    except Exception as e:
        logger.exception(f'[{job_id}] exception was raised while comparing alignments')

        response_data = {
            'results': {'ok': False, 'exception': str(e)}
        }
        result_files = dict()

    logger.debug(f'[{job_id}] comparison finished with result {response_data}')
    result_id = await insert_comparison(job_id, response_data, result_files)
    logger.info(f'[{job_id}] inserted result as {result_id}')

    await send_finished_comparison(job_id, result_id)


@app.task(name='compare_alignments', queue='server_comparer')
def compare_alignments_sync(data):
    loop = get_event_loop()
    return loop.run_until_complete(compare_alignments_and_send(data))



async def send_finished_alignment(job_id, result_id):
    url = config['FINISHED_ALIGNMENT_URL']
    return await send_finished_job(job_id, result_id, url)

async def send_finished_comparison(job_id, result_id):
    url = config['FINISHED_COMPARISON_URL']
    return await send_finished_job(job_id, result_id, url)

async def send_finished_job(job_id, result_id, url):
    headers = {'content-type': 'application/json'}
    data = {'job_id': job_id, 'result_id': str(result_id)}

    async with ClientSession(headers=headers) as session:
        async with session.post(url, data=json_dumps(data)) as response:
            response.raise_for_status()

if __name__ == '__main__':
    process_alignment.delay(data={"db": 'Test'})

