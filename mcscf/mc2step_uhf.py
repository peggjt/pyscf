#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

import time
import numpy
import scipy.linalg
import pyscf.lib.logger as logger
from pyscf.mcscf import mc1step
from pyscf.mcscf import mc1step_uhf

def kernel(casscf, mo_coeff, tol=1e-7, macro=30, micro=4,
           ci0=None, callback=None, verbose=None,
           dump_chk=True, dump_chk_ci=False):
    if verbose is None:
        verbose = casscf.verbose
    log = logger.Logger(casscf.stdout, verbose)
    cput0 = (time.clock(), time.time())
    log.debug('Start 2-step CASSCF')

    mo = mo_coeff
    nmo = mo[0].shape[1]
    ncore = casscf.ncore
    ncas = casscf.ncas
    eris = casscf.ao2mo(mo)
    e_tot, e_ci, fcivec = casscf.casci(mo, ci0, eris)
    log.info('CASCI E = %.15g', e_tot)
    if ncas == nmo:
        return True, e_tot, e_ci, fcivec, mo
    elast = e_tot
    conv = False
    toloose = casscf.conv_tol_grad
    totmicro = totinner = 0
    casdm1 = (0,0)

    t2m = t1m = log.timer('Initializing 2-step CASSCF', *cput0)
    for imacro in range(macro):
        ninner = 0
        t3m = t2m
        casdm1_old = casdm1
        casdm1, casdm2 = casscf.fcisolver.make_rdm12s(fcivec, ncas, casscf.nelecas)
        norm_ddm =(numpy.linalg.norm(casdm1[0] - casdm1_old[0])
                 + numpy.linalg.norm(casdm1[1] - casdm1_old[1]))
        t3m = log.timer('update CAS DM', *t3m)
        for imicro in range(micro):

            rota = casscf.rotate_orb_cc(mo, casdm1, casdm2, eris, verbose=log)
            u, g_orb, njk = rota.next()
            rota.close()
            ninner += njk
            norm_t = numpy.linalg.norm(u-numpy.eye(nmo))
            norm_gorb = numpy.linalg.norm(g_orb)
            t3m = log.timer('orbital rotation', *t3m)

            mo = list(map(numpy.dot, mo, u))

            eris = None
            eris = casscf.ao2mo(mo)
            t3m = log.timer('update eri', *t3m)

            log.debug('micro %d  |u-1|= %4.3g  |g[o]|= %4.3g  |dm1|= %4.3g', \
                      imicro, norm_t, norm_gorb, norm_ddm)

            if callable(callback):
                callback(locals())

            t2m = log.timer('micro iter %d'%imicro, *t2m)
            if norm_t < toloose or norm_gorb < toloose:
                break

        totinner += ninner
        totmicro += imicro+1

        e_tot, e_ci, fcivec = casscf.casci(mo, fcivec, eris)
        log.info('macro iter %d (%d JK  %d micro), CASSCF E = %.15g  dE = %.8g',
                 imacro, ninner, imicro+1, e_tot, e_tot-elast)
        log.info('               |grad[o]|= %4.3g  |dm1|= %4.3g',
                 norm_gorb, norm_ddm)
        log.debug('CAS space CI energy = %.15g', e_ci)
        log.timer('CASCI solver', *t3m)
        t2m = t1m = log.timer('macro iter %d'%imacro, *t1m)

        if (abs(elast - e_tot) < tol and
            norm_gorb < toloose and norm_ddm < toloose):
            conv = True
        else:
            elast = e_tot

        if dump_chk:
            casscf.dump_chk(locals())

        if conv:
            break

    if conv:
        log.info('2-step CASSCF converged in %d macro (%d JK %d micro) steps',
                 imacro+1, totinner, totmicro)
    else:
        log.info('2-step CASSCF not converged, %d macro (%d JK %d micro) steps',
                 imacro+1, totinner, totmicro)
    log.note('2-step CASSCF, energy = %.15g', e_tot)
    log.timer('2-step CASSCF', *cput0)
    return conv, e_tot, e_ci, fcivec, mo


if __name__ == '__main__':
    from pyscf import gto
    from pyscf import scf
    from pyscf.mcscf import addons

    mol = gto.Mole()
    mol.verbose = 0
    mol.output = None#"out_h2o"
    mol.atom = [
        ['H', ( 1.,-1.    , 0.   )],
        ['H', ( 0.,-1.    ,-1.   )],
        ['H', ( 1.,-0.5   ,-1.   )],
        ['H', ( 0.,-0.5   ,-1.   )],
        ['H', ( 0.,-0.5   ,-0.   )],
        ['H', ( 0.,-0.    ,-1.   )],
        ['H', ( 1.,-0.5   , 0.   )],
        ['H', ( 0., 1.    , 1.   )],
    ]

    mol.basis = {'H': 'sto-3g',
                 'O': '6-31g',}
    mol.charge = 1
    mol.spin = 1
    mol.build()

    m = scf.UHF(mol)
    ehf = m.scf()
    emc = kernel(mc1step_uhf.CASSCF(m, 4, (2,1)), m.mo_coeff, verbose=4)[1]
    print(ehf, emc, emc-ehf)
    print(emc - -2.9782774463926618)


    mol.atom = [
        ['O', ( 0., 0.    , 0.   )],
        ['H', ( 0., -0.757, 0.587)],
        ['H', ( 0., 0.757 , 0.587)],]
    mol.basis = {'H': 'cc-pvdz',
                 'O': 'cc-pvdz',}
    mol.charge = 1
    mol.spin = 1
    mol.build()

    m = scf.UHF(mol)
    ehf = m.scf()
    mc = mc1step_uhf.CASSCF(m, 4, (2,1))
    mc.verbose = 4
    mo = addons.sort_mo(mc, m.mo_coeff, (3,4,6,7), 1)
    emc = mc.mc2step(mo)[0]
    print(ehf, emc, emc-ehf)
    #-75.631870606190233, -75.573930418500652, 0.057940187689581535
    print(emc - -75.573930418500652, emc - -75.648547447838951)


