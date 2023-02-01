import logging
import os
import re
import numpy as np
import shutil
import tarfile
import tempfile
from urllib import request as request

import openbabel
from openbabel import pybel
from rdkit import Chem

from ase.units import Debye, Bohr, Hartree, eV, Ang
from ase.io.extxyz import read_xyz

logging.getLogger("").setLevel(logging.CRITICAL)
logging.disable(logging.CRITICAL)


atomic_atom = {'1':'H','6':'C','7':'N','8':'O','9':'F'}
atom_atomic = {'H':1,'C':6,'N':7,'O':8,'F':9}

conversions = [1., 1., 1., 1., Bohr ** 3 / Ang ** 3,
                   Hartree / eV, Hartree / eV, Hartree / eV,
                   Bohr ** 2 / Ang ** 2, Hartree / eV,
                   Hartree / eV, Hartree / eV, Hartree / eV,
                   Hartree / eV, 1.]

prop_names = ['rcA', 'rcB', 'rcC', 'mu', 'alpha', 'homo', 'lumo',
              'gap', 'r2', 'zpve', 'energy_U0', 'energy_U', 'enthalpy_H',
              'free_G', 'Cv']

def _load_evilmols():
    print("Downloading list of uncharacterized molecules...")
    at_url = "https://springernature.figshare.com/ndownloader/files/3195404"
    tmpdir = tempfile.mkdtemp("gdb9")
    tmp_path = os.path.join(tmpdir, "uncharacterized.txt")

    request.urlretrieve(at_url, tmp_path)
    print("Done.")

    evilmols = []
    with open(tmp_path) as f:
        lines = f.readlines()
        for line in lines[9:-1]:
            evilmols.append(int(line.split()[0]))
    return np.array(evilmols)

def process_qm9(dataset='qm9', save_path=''):

    print('Download qm9 data')

    tmpdir = tempfile.mkdtemp("gdb9")
    tar_path = os.path.join(tmpdir, "gdb9.tar.gz")
    raw_path = os.path.join(tmpdir, "gdb9_xyz")
    url = "https://springernature.figshare.com/ndownloader/files/3195389"

    request.urlretrieve(url, tar_path)
    print("Done.")

    print("Extracting files...")
    tar = tarfile.open(tar_path)
    tar.extractall(raw_path)
    tar.close()
    print("Done.")

    print("Parse xyz files...")
    ordered_files = sorted(
        os.listdir(raw_path), key=lambda x: (int(re.sub("\D", "", x)), x)
    )

    # QM9 has 133,885 files
    irange = np.arange(len(ordered_files), dtype=np.int)

    # Remove 3054 files with unstable geometric 
    remove = _load_evilmols()

    irange = np.setdiff1d(irange, remove - 1)

    # Keep exactly 130831 files in QM9
    assert len(irange) == 130831

    all_struct = []
    error = 0
    for idx in irange:
        if idx % 10000 == 0:
            print('Parse {:6d} / 130831 QM9 data'.format(idx+1))

        xyzfile = os.path.join(raw_path, ordered_files[idx])
        properties={}
        tmp = os.path.join(tmpdir, "tmp.xyz")
        with open(xyzfile, 'r') as f:
            lines = f.readlines()
            l = lines[1].split()[2:]
            for pn, p, c in zip(prop_names, l, conversions):
                properties[pn] = float(p) * c
            with open(tmp, "wt") as fout:
                for line in lines:
                    fout.write(line.replace('*^', 'e'))
        
        mol = next(pybel.readfile("xyz", tmp))
        
        atoms = [x.OBAtom for x in mol.atoms]
        
        atomics = [x.GetAtomicNum() for x in atoms]
        atomic_symbols = [atomic_atom[str(x)] for x in atomics]
        
        ring_info = [1  if at.IsInRing() else 0 for at in atoms]
        aromatic = [1  if at.IsAromatic() else 0 for at in atoms]

        coordinates = [[x.GetX(), x.GetY(), x.GetZ()] for x in atoms]

        nstruct = {'id': idx, 'Properties': properties,
                'Atoms': atomic_symbols, 'Atomic':atomics,
                'Coords': coordinates, 
                'Ring': ring_info, 'Aromatic':aromatic, } 
        
        all_struct.append(nstruct)

    print("Saving file and removing temp dirs")

    dataset_file = os.path.join(save_path, dataset, dataset + '_data_energy.npy')
    if not os.path.exists(os.path.join(save_path, dataset)):
        os.makedirs(os.path.join(save_path, dataset))
        
    np.save(dataset_file, all_struct)

    shutil.rmtree(tmpdir, ignore_errors=True)

    print("Finished clearing temp dirs")