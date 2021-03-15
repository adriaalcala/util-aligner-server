import pandas as pd

from server.scores.common import reverse_alignment_series, add_alignment_image
from ppi_sources.network import VirusHostNetwork


def add_is_edge_column(image, net_igraph):
    if image.empty:
        return image.assign(is_edge = pd.Series([], dtype=bool))

    return image \
        .assign(is_edge =
            image.apply(lambda row:
                    pd.notna(row.source) and
                    pd.notna(row.target) and
                    net_igraph[row.source, row.target] > 0,
                axis='columns'))


def compute_ec_image_scores(net1, net2, alignment):
    alignment_series = alignment.iloc[:, 0]

    # restrict the alignment to the given networks
    valid_source_ix = alignment_series.index.to_series().isin(frozenset(net1.igraph.vs['name'])).to_numpy()
    valid_image_ix = alignment_series.isin(frozenset(net2.igraph.vs['name'])).to_numpy()

    alignment_series = alignment_series.loc[valid_source_ix & valid_image_ix]

    invalid_images = alignment.iloc[:, 0].loc[valid_source_ix & ~valid_image_ix].unique().tolist()

    unaligned_nodes = list(frozenset(net1.igraph.vs['name']) - frozenset(alignment_series.index.to_numpy()))

    image = add_alignment_image(net1.to_dataframe(), alignment_series) \
        .pipe(add_is_edge_column, net2.igraph)

    preserved_edges = image.loc[:, ['source_orig', 'target_orig', 'is_edge']] \
        .groupby(['source_orig', 'target_orig']) \
        .all()

    num_preserved_edges = int(preserved_edges.is_edge.sum())

    non_preserved_edges = preserved_edges.reset_index() \
        .loc[lambda df: ~df.is_edge, ['source_orig', 'target_orig']] \
        .astype(str)

    unaligned_edges = image.loc[image.source.isna() | image.target.isna(), ['source_orig', 'target_orig']] \
        .astype(str)

    min_es = net1.igraph.ecount() if net1.igraph.vcount() <= net2.igraph.vcount() else net2.igraph.ecount()

    return {
        'invalid_images': pd.Series(invalid_images, name='invalid_images'),
        'num_invalid_images': len(invalid_images),

        'unaligned_nodes': pd.Series(unaligned_nodes, name='unaligned_nodes'),
        'num_unaligned_nodes': len(unaligned_nodes),

        'unaligned_edges': unaligned_edges,
        'num_unaligned_edges': len(unaligned_edges),

        'non_preserved_edges': non_preserved_edges,
        'num_preserved_edges': num_preserved_edges,

        'min_n_edges': min_es,
        'ec_score': num_preserved_edges/min_es if min_es > 0 else -1.0,
    }


def compute_ec_preimage_scores(net1, net2, alignment):
    alignment_series = reverse_alignment_series(alignment.iloc[:, 0])
    valid_preimage_ix = alignment_series.isin(frozenset(net1.igraph.vs['name'])).to_numpy()
    alignment_series = alignment_series.loc[valid_preimage_ix]

    # we dropna() here, but not in compute_ec_image_scores

    preimage = add_alignment_image(net2.to_dataframe(), alignment_series) \
        .dropna() \
        .pipe(add_is_edge_column, net1.igraph)

    reflected_edges = preimage.loc[:, ['source_orig', 'target_orig', 'is_edge']] \
        .groupby(['source_orig', 'target_orig']) \
        .all()

    num_reflected_edges = int(reflected_edges.is_edge.sum())

    non_reflected_edges = reflected_edges.reset_index() \
        .loc[lambda df: ~df.is_edge, ['source_orig', 'target_orig']] \
        .astype(str)

    return {
        'non_reflected_edges': non_reflected_edges,
        'num_reflected_edges': num_reflected_edges,
    }


def compute_ec_scores(net1, net2, alignment):
    scores = {}
    scores.update(compute_ec_image_scores(net1, net2, alignment))
    scores.update(compute_ec_preimage_scores(net1, net2, alignment))

    if isinstance(net1, VirusHostNetwork) and isinstance(net2, VirusHostNetwork):
        scores.update({
            'host_ec_data':         compute_ec_scores(net1.host_net, net2.host_net, alignment),
            'virus_ec_data':        compute_ec_scores(net1.virus_net, net2.virus_net, alignment),
            'vh_bipartite_ec_data': compute_ec_scores(net1.vh_bipartite_net, net2.vh_bipartite_net, alignment)
        })

    return scores
