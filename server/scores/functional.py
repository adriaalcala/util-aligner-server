from collections import Counter
from math import isnan
import pandas as pd

from go_tools import init_default_hrss
from semantic_similarity import JaccardSim



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


def compute_fc(alignment, ontology_mapping, dissim):
    fc_sum = 0
    fc_len = 0

    results = []

    for p1_name, p2_name in alignment.itertuples(name=None, index=True):
        gos1 = frozenset(ontology_mapping.get(p1_name, []))
        gos2 = frozenset(ontology_mapping.get(p2_name, []))

        fc = dissim(gos1, gos2)

        if not isnan(fc):
            results.append((p1_name, p2_name, fc))
            fc_sum += fc
            fc_len += 1

    fc_avg = fc_sum/fc_len if fc_len > 0 else -1
    results_df = pd.DataFrame(results, columns=[alignment.index.name, alignment.columns[0], 'fc'])
    return results_df, fc_avg


def compute_bitscore_fc(alignment, bitscore_matrix):
    bitscore_df = bitscore_matrix.to_dataframe()

    alignment_df = alignment.reset_index()

    col_names = list(bitscore_df.columns[:2])
    alignment_df.columns = col_names
    bitscore_df = bitscore_df.set_index(col_names)

    relevant_bitscores = bitscore_df.join(alignment_df.set_index(col_names), how='inner')

    return float(relevant_bitscores.bitscore.sum() / bitscore_df.bitscore.max()) \
        if not relevant_bitscores.empty else -1


jaccard_sim = JaccardSim().compare
hrss_bma_sim = init_default_hrss().compare

def compute_fc_scores(net1, net2, alignment, bitscore_matrix, ontology_mapping):
    bitscore_fc = compute_bitscore_fc(alignment, bitscore_matrix)

    fc_data = {'fc_score_bitscore': bitscore_fc}

    if ontology_mapping:
        fc_values_jaccard,  fc_jaccard  = compute_fc(alignment, ontology_mapping, jaccard_sim)
        fc_values_hrss_bma, fc_hrss_bma = compute_fc(alignment, ontology_mapping, hrss_bma_sim)

        ann_freqs_net1, no_go_prots_net1 = count_annotations(net1, ontology_mapping)
        ann_freqs_net2, no_go_prots_net2 = count_annotations(net2, ontology_mapping)

        fc_data.update({
            'fc_score_jaccard': fc_jaccard,
            'fc_values_jaccard': fc_values_jaccard,
            'fc_score_hrss_bma': fc_hrss_bma,
            'fc_values_hrss_bma': fc_values_hrss_bma,
            'unannotated_prots_net1': pd.Series(list(no_go_prots_net1), name='unannotated_prots_net1'),
            'unannotated_prots_net2': pd.Series(list(no_go_prots_net2), name='unannotated_prots_net2'),
            'ann_freqs_net1': {str(ann_cnt): freq for ann_cnt, freq in ann_freqs_net1.items()},
            'ann_freqs_net2': {str(ann_cnt): freq for ann_cnt, freq in ann_freqs_net2.items()}
        })

    return fc_data
