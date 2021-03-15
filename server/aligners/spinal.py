from itertools import islice
from os import path

from server.aligners.aligner import Aligner
from server.util import iter_csv


class Spinal(Aligner):
    def __init__(self, alpha=0.7):
        super().__init__()
        self.alpha = alpha

    @property
    def name(self):
        return 'spinal'

    @property
    def cmd(self):
        return [
            './spinal', '-I', '-ns',
            'net1.gml', 'net2.gml', 'blast-net1-net2.csv',
            'alignment-net1-net2.csv',
            str(self.alpha)
        ]

    def write_files(self, run_dir_path, net1, net2, blast_net1_net2):
        super().write_files(run_dir_path)

        self.logger.debug(f'run_{self.name} @ {run_dir_path}: writing net1.gml')
        net1_path = path.join(run_dir_path, 'net1.gml')
        net1.write_gml(net1_path)

        self.logger.debug(f'run_{self.name} @ {run_dir_path}: writing net2.gml')
        net2_path = path.join(run_dir_path, 'net2.gml')
        net2.write_gml(net2_path)

        self.logger.debug(f'run_{self.name} @ {run_dir_path}: writing blast-net1-net2.csv')
        blast_path = path.join(run_dir_path, 'blast-net1-net2.csv')
        blast_net1_net2.write_tricol(blast_path, by='index', sep=' ')

    def iter_alignment_ids(self, execution_dir, file_name='alignment-net1-net2.csv'):
        alignment_path = path.join(execution_dir, file_name)

        # ignore the first two lines, they seem to be comments
        csv_rows = iter_csv(alignment_path, delimiter=' ')
        csv_rows = islice(csv_rows, 2, None)

        for p1id, p2id in csv_rows:
            yield int(p1id), int(p2id)

    def iter_alignment(self, net1, net2, execution_dir, file_name='alignment-net1-net2.csv'):
        net1_vs = net1.igraph.vs
        net2_vs = net2.igraph.vs

        for p1id, p2id in self.iter_alignment_ids(execution_dir, file_name):
            yield net1_vs[p1id]['name'], net2_vs[p2id]['name']

    def import_alignment(self, net1, net2, execution_dir, file_name='alignment-net1-net2.csv'):
        header = (net1.name, net2.name)
        return header, list(self.iter_alignment(net1, net2, execution_dir, file_name))
