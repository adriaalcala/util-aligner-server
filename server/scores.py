from collections import Counter
from itertools import chain
from math import inf, isinf

from go_tools import get_curated_frequencies_path
import geneontology as godb
import semantic_similarity as semsim

from util import write_tsv_to_string

def compute_ec_scores(net1, net2, alignment):
    net1 = net1.igraph
    net2 = net2.igraph
    min_es = net1.ecount() if net1.vcount() <= net2.vcount() else net2.ecount()

    result = {
        'min_n_edges': min_es
    }

    alignment = dict(alignment)

    unaligned_edges_net1 = set()
    unaligned_nodes_net1 = set()
    unknown_nodes_net2 = set()

    # compute EC and non_preserved_edges

    num_preserved_edges = 0
    non_preserved_edges = set()

    for e in net1.es:
        p1_id, p2_id = e.tuple
        p1_name, p2_name = net1.vs[p1_id]['name'], net1.vs[p2_id]['name']

        fp1_name, fp2_name = alignment.get(p1_name), alignment.get(p2_name)
        if fp1_name is None:
            unaligned_nodes_net1.add(p1_name)
            unaligned_edges_net1.add((p1_name, p2_name))
            continue
        if fp2_name is None:
            unaligned_nodes_net1.add(p2_name)
            unaligned_edges_net1.add((p1_name, p2_name))
            continue

        fp1s, fp2s = net2.vs.select(name=fp1_name), net2.vs.select(name=fp2_name)

        if len(fp1s) == 0:
            unknown_nodes_net2.add(fp1_name)
            continue
        if len(fp2s) == 0:
            unknown_nodes_net2.add(fp2_name)
            continue

        if net2.get_eid(fp1s[0].index, fp2s[0].index, directed=False, error=False) >= 0:
            num_preserved_edges += 1
        else:
            non_preserved_edges.add((p1_name, p2_name))

    def node_preimage(p_name):
        selections = (net1.vs.select(name=preim_name) for preim_name, value in alignment.items() if value == p_name)
        return [v.index for v in chain.from_iterable(selections)]

    # compute non_reflected_edges

    non_reflected_edges = set()

    for e in net2.es:
        p1_id, p2_id = e.tuple
        p1_name, p2_name = net2.vs[p1_id]['name'], net2.vs[p2_id]['name']

        preim_p1_ids = node_preimage(p1_name)
        preim_p2_ids = node_preimage(p2_name)

        if all(net1.get_eid(preim_p1_id, preim_p2_id, directed=False, error=False) < 0
                for preim_p1_id in preim_p1_ids
                for preim_p2_id in preim_p2_ids):
            non_reflected_edges.add((p1_name, p2_name))

    result.update({
        'unaligned_edges_net1': list(unaligned_edges_net1),
        'unaligned_nodes_net1': list(unaligned_nodes_net1),
        'unknown_nodes_net2': list(unknown_nodes_net2),
        'non_preserved_edges': list(non_preserved_edges),
        'non_reflected_edges': list(non_reflected_edges),
        'num_unaligned_edges_net1': len(unaligned_edges_net1),
        'num_unaligned_nodes_net1': len(unaligned_nodes_net1),
        'num_unknown_nodes_net2': len(unknown_nodes_net2),
        'num_non_preserved_edges': len(non_preserved_edges),
        'num_non_reflected_edges': len(non_reflected_edges),
        'num_preserved_edges': num_preserved_edges,
        'ec_score': num_preserved_edges/min_es if min_es > 0 else -1.0,
    })

    return result

def count_annotations(net, ontology_mapping):
    ann_freqs = Counter()
    no_go_prots = set()

    for p in net.igraph.vs:
        p_name = p['name']
        gos = frozenset(ontology_mapping.get(p_name, []))

        ann_freqs[len(gos)] += 1

        if not gos:
            no_go_prots.add(p_name)

    return ann_freqs, no_go_prots


def compute_fc(net1, net2, alignment, ontology_mapping, dissim):
    fc_sum = 0
    fc_len = 0

    results = []

    for p1_name, p2_name in alignment:
        gos1 = frozenset(ontology_mapping.get(p1_name, []))
        gos2 = frozenset(ontology_mapping.get(p2_name, []))

        fc = dissim(gos1, gos2)

        if fc is not None:
            results.append((p1_name, p2_name, fc))
            fc_sum += fc
            fc_len += 1

    fc_avg = fc_sum/fc_len if fc_len > 0 else -1
    return results, fc_avg


def jaccard_dissim(gos1, gos2):
    if gos1 and gos2:
        len_intersection = len(gos1.intersection(gos2))
        len_union = len(gos1.union(gos2))
        return len_intersection / len_union
    else:
        return None

def init_hrss_sim(agg = semsim.agg_bma_max):
    import geneontology as godb

    go_onto = godb.load_go_obo()
    go_is_a_g = godb.onto_rel_graph(go_onto)

    ic = semsim.init_ic(get_curated_frequencies_path())

    def pair_dissim(go1, go2):
        return semsim.get_hrss_sim(go_is_a_g, ic, go1, go2)

    def agg_dissim(gos1, gos2):
        return agg(pair_dissim, gos1, gos2)

    def dissim(gos1, gos2):
        if gos1 and gos2:
            r = min(semsim.namespace_wise_comparisons(go_onto, agg_dissim, gos1, gos2), default=inf)
            return r if not isinf(r) else None
        else:
            return None

    return dissim

hrss_bma_sim = init_hrss_sim(agg = semsim.agg_bma_max)

def compute_fc_scores(net1, net2, alignment, ontology_mapping):
    fc_values_jaccard, fc_jaccard = compute_fc(net1, net2, alignment, ontology_mapping, jaccard_dissim)

    fc_values_hrss_bma, fc_hrss_bma = compute_fc(net1, net2, alignment, ontology_mapping, hrss_bma_sim)

    ann_freqs_net1, no_go_prots_net1 = count_annotations(net1, ontology_mapping)
    ann_freqs_net2, no_go_prots_net2 = count_annotations(net2, ontology_mapping)

    return {
        'fc_score_jaccard': fc_jaccard,
        'fc_values_jaccard': fc_values_jaccard,
        'fc_score_hrss_bma': fc_hrss_bma,
        'fc_values_hrss_bma': fc_values_hrss_bma,
        'unannotated_prots_net1': list(no_go_prots_net1),
        'unannotated_prots_net2': list(no_go_prots_net2),
        'ann_freqs_net1': {str(ann_cnt): freq for ann_cnt, freq in ann_freqs_net1.items()},
        'ann_freqs_net2': {str(ann_cnt): freq for ann_cnt, freq in ann_freqs_net2.items()}
    }


def compute_scores(net1, net2, alignment, ontology_mapping):
    ec_data = compute_ec_scores(net1, net2, alignment)
    fc_data = compute_fc_scores(net1, net2, alignment, ontology_mapping)

    return {
        'ec_data': ec_data,
        'fc_data': fc_data
    }


def split_score_data_as_tsvs(scores):
    tsvs = dict()

    def split_key(src_dict, key):
        tsvs[key + '_tsv'] = write_tsv_to_string(src_dict[key])
        src_dict[key] = None

    ec_data = scores['ec_data']

    split_key(ec_data, 'unaligned_edges_net1')
    split_key(ec_data, 'unaligned_nodes_net1')
    split_key(ec_data, 'non_preserved_edges')
    split_key(ec_data, 'non_reflected_edges')

    fc_data = scores['fc_data']

    split_key(fc_data, 'fc_values_jaccard')
    split_key(fc_data, 'fc_values_hrss_bma')

    return tsvs
