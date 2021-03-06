from asyncio import coroutine
from os import path
import json

from server.sources.network import read_net_tsv_edgelist
from server.sources.bitscore import read_tricol_bitscores


class IsobaseLocal(object):
    def __init__(self, base_path):
        self.base_path = base_path

    def _check_valid_species(self, species_name):
        if not species_name.isalnum():
            raise ValueError(f'invalid species name: {species_name}')

    @coroutine
    def __aenter__(self):
        return self

    @coroutine
    def __aexit__(self, exc_type, exc, tb):
        pass

    @coroutine
    def get_network(self, species_name):
        self._check_valid_species(species_name)
        species_path = path.join(self.base_path, f'{species_name}.tab')

        if not path.isfile(species_path):
            raise LookupError(f'network file for {species_name} was not found')

        return read_net_tsv_edgelist(species_name, species_path)

    @coroutine
    def get_bitscore_matrix(self, net1, net2):
        if net1.name == net2.name:
            matrix_path = path.join(self.base_path, f'{net1.name}-blast.tab')

            if not path.isfile(matrix_path):
                raise LookupError(f'score matrix file for {net1.name} was not found')
        else:
            matrix_path = path.join(self.base_path, f'{net1.name}-{net2.name}-blast.tab')

            if not path.isfile(matrix_path):
                raise LookupError(f'score matrix file for {net1.name}-{net2.name} was not found')

        return read_tricol_bitscores(matrix_path, net1=net1, net2=net2)

    @coroutine
    def get_ontology_mapping(self, networks=None):
        # TODO: Update go.json to a newer go.obo and return its contents here
        return {}
