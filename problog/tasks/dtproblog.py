#! /usr/bin/env python

"""
ProbLog command-line interface.

Copyright 2015 KU Leuven, DTAI Research Group

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import print_function

import sys
import logging

from problog.program import PrologFile
from problog.engine import DefaultEngine
from problog.logic import Term, Constant
from problog.errors import process_error
from problog import get_evaluatables, get_evaluatable
from problog.util import init_logger, Timer
from problog.program import ExtendedPrologFactory


def main(argv, result_handler=None):
    args = argparser().parse_args(argv)
    inputfile = args.inputfile

    init_logger(args.verbose)

    if result_handler is None:
        if args.web:
            result_handler = print_result_json
        else:
            result_handler = print_result

    if args.output is not None:
        outf = open(args.output, 'w')
    else:
        outf = sys.stdout

    try:

        with Timer('Parse input'):
            pl = PrologFile(inputfile, factory=DTProbLogFactory())

            eng = DefaultEngine()
            db = eng.prepare(pl)

        decisions = dict((d[0], None) for d in eng.query(db, Term('decision', None)))
        utilities = dict(eng.query(db, Term('utility', None, None)))

        for d in decisions:
            db += d.with_probability(Constant(0.5))

        gp = eng.ground_all(db, target=None, queries=utilities.keys(), evidence=decisions.items())

        knowledge = get_evaluatable(args.koption).create_from(gp)

        with Timer('Optimize'):
            if args.search == 'local':
                result = search_local(knowledge, decisions, utilities, **vars(args))
            else:
                result = search_exhaustive(knowledge, decisions, utilities, **vars(args))

        print (*result)

        # result_handler((True, best_choice), outf)
    except Exception as err:
        result_handler((False, err), outf)

    if args.output is not None:
        outf.close()


def evaluate(formula, decisions, utilities):
    result = formula.evaluate(evidence=decisions)

    score = 0.0
    for r in result:
        score += result[r] * float(utilities[r])
    return score


def search_exhaustive(formula, decisions, utilities, verbose=0, **kwargs):
    stats = {'eval': 0}
    best_score = None
    best_choice = None
    decision_names = decisions.keys()
    for i in range(0, 1 << len(decisions)):
        choices = num2bits(i, len(decisions))

        evidence = dict(zip(decision_names, choices))
        score = evaluate(formula, evidence, utilities)
        stats['eval'] += 1
        if best_score is None or score > best_score:
            best_score = score
            best_choice = dict(evidence)
            logging.getLogger('problog').debug('Improvement: %s -> %s' % (best_choice, best_score))
    return best_choice, best_score, stats


def search_local(formula, decisions, utilities, verbose=0, **kwargs):
    stats = {'eval': 0}

    for key in decisions:
        if key in utilities and float(utilities[key]) > 0:
            decisions[key] = True
        else:
            decisions[key] = False

    best_score = evaluate(formula, decisions, utilities)

    last_update = None
    stop = False
    while not stop:
        for key in decisions:
            if last_update == key:
                stop = True
                break
            # Flip a decision
            decisions[key] = not decisions[key]
            flip_score = evaluate(formula, decisions, utilities)
            stats['eval'] += 1
            if flip_score <= best_score:
                decisions[key] = not decisions[key]
            else:
                last_update = key
                best_score = flip_score
                logging.getLogger('problog').debug('Improvement: %s -> %s' % (decisions, best_score))
        if last_update is None:
            stop = True

    return decisions, best_score, stats


def num2bits(n, nbits):
    bits = [False] * nbits
    for i in range(1, nbits + 1):
        bits[nbits - i] = bool(n % 2)
        n >>= 1
    return bits


def print_result(result, output=sys.stdout):
    success, result = result
    if success:
        if result is None:
            print ('%% The model is not satisfiable.', file=output)
        else:
            for atom in result.items():
                print('%s: %s' % atom, file=output)
        return 0
    else:
        print(process_error(result), file=output)
        return 1


def print_result_json(d, output):
    """Pretty print result.

    :param d: result from run_problog
    :param output: output file
    :param precision:
    :return:
    """
    import json
    result = {}
    success, d = d
    if success:
        result['SUCCESS'] = True
        if d is not None:
            result['atoms'] = list(map(lambda n: (str(-n), False) if n.is_negated() else (str(n), True), d))
    else:
        result['SUCCESS'] = False
        result['err'] = process_error(d)
        result['original'] = str(d)
    print (json.dumps(result), file=output)
    return 0


class DTProbLogFactory(ExtendedPrologFactory):

    def build_probabilistic(self, operand1, operand2, location=None, **extra):
        if str(operand1.functor) in 'd?':
            return Term('decision', operand2, location=location)
        else:
            return ExtendedPrologFactory.build_probabilistic(self, operand1, operand2, location, **extra)


def argparser():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('inputfile')
    parser.add_argument('--knowledge', '-k', dest='koption',
                        choices=get_evaluatables(),
                        default=None, help="Knowledge compilation tool.")
    parser.add_argument('-s', '--search', choices=('local', 'exhaustive'), default='exhaustive')
    parser.add_argument('-v', '--verbose', action='count', help='Set verbosity level')
    parser.add_argument('-o', '--output', type=str, default=None,
                        help='Write output to given file (default: write to stdout)')
    parser.add_argument('--web', action='store_true', help=argparse.SUPPRESS)
    return parser


if __name__ == '__main__':
    main(sys.argv[1:])
