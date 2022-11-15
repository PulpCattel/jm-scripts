#!/usr/bin/env python3
"""
Standalone script with no dependencies.
The only thing you need is an orderbook.json file.
To get that:
    * Run the ob-watcher.py script yourself and export it.
    * Find a public orderbook you trust and export it from there.
    * For testing, you can build the JSON file yourself, ideally a script should be made to make it trivial.
"""
import sys
from argparse import ArgumentParser, Namespace, ArgumentTypeError
from decimal import Decimal
from enum import Enum
from json import loads
from logging import Logger, getLogger, StreamHandler, Formatter
from os.path import isfile
from random import random, choices, randrange
from statistics import stdev, mean
from time import monotonic
from typing import List, Dict, Any, Tuple

DESCRIPTION = """
Given an orderbook file as JSON, e.g., exported from ob-watcher.py, run 
multiple simulations to estimate the picking chances of each maker offer.
"""

# Same as JoinMarket default
BONDLESS_ALLOWANCE = 0.125


class ExitStatus(Enum):
    """
    Exit status codes.
    """
    SUCCESS = 0
    FAILURE = 1
    ARGERROR = 2


def get_logger(verbose: bool) -> Logger:
    logger = getLogger(__name__)
    ch = StreamHandler()
    if verbose:
        # DEBUG
        logger.setLevel(10)
    else:
        # INFO
        logger.setLevel(20)
    ch.setFormatter(Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%m/%d/%Y %I:%M:%S'))
    logger.addHandler(ch)
    return logger


def orderbook(path: str) -> Dict[str, Any]:
    """
    Open given filepath and return orderbook content.
    """
    if not isfile(path):
        raise ArgumentTypeError(f"{path} is not a valid path")
    try:
        with open(path, "r", encoding="UTF-8") as ob:
            return loads(ob.read())
    except Exception as exc:
        raise ArgumentTypeError('Not a valid orderbook JSON file') from exc


def max_fees(fees: str) -> Tuple[int, float]:
    abs_fee, rel_fee = fees.split(',')
    try:
        return int(abs_fee), float(rel_fee)
    except Exception as exc:
        raise ArgumentTypeError('Given max fees are not valid') from exc


def get_args() -> Namespace:
    parser = ArgumentParser(
        usage="jmsim.py [options] orderbook",
        description=DESCRIPTION,
    )
    parser.add_argument(
        "orderbook",
        action="store",
        type=orderbook,
        help="Path to the exported orderbook in JSON format",
    )
    parser.add_argument(
        "-n",
        "--maker-count",
        action="store",
        type=int,
        dest="maker_count",
        help="Number of counterparties to use in CoinJoin simulation, default 10",
        default=10,
    )
    parser.add_argument(
        "-t",
        "--trials",
        action="store",
        type=int,
        dest="trials",
        help="Number of trials to estimate picking chances, default 10",
        default=10,
    )
    parser.add_argument(
        "-s",
        "--sample_size",
        action="store",
        type=int,
        dest="sample_size",
        help="Number of CoinJoin simulations for each trial, default 100 times the number of (filtered) offers in the "
             "orderbook",
    )
    parser.add_argument(
        "-b",
        "--bondless",
        action="store",
        type=float,
        dest="bondless_allowance",
        default=BONDLESS_ALLOWANCE,
        help=f"Bondless allowance to use for CoinJoin simulation (instead of bondless_makers_allowance default, {BONDLESS_ALLOWANCE})",
    )
    parser.add_argument(
        "-a",
        "--amount",
        action="store",
        type=int,
        dest="amount",
        help="Filter orderbook based on CoinJoin amount in sats. If an offer can't satisfy this amount, "
             "it's disregarded. Default does not filter",
    )
    parser.add_argument(
        "-f",
        "--max-fees",
        action="store",
        type=max_fees,
        dest="max_fees",
        help="Filter the orderbook based on maximum fees asked (naively, does not take into account the CoinJoin "
             "amount). Specify both absolute and relative fees comma separated, e.g., 1000,0.002 (default does not "
             "filter)",
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help="Increase logging verbosity to DEBUG",
    )
    return parser.parse_args()


def filter_ob_by_fees(offers: List[Dict[str, Any]], max_abs: int, max_rel: float) -> List[Dict[str, Any]]:
    """
    Return a new list of offers naively filtered by fees.
    """
    filtered_offers = []
    for offer in offers:
        cjfee = float(offer["cjfee"])
        if "absoffer" in offer["ordertype"]:
            if cjfee > max_abs:
                continue
        elif "reloffer" in offer["ordertype"]:
            if cjfee > max_rel:
                continue
        else:
            # It's an invalid order type
            continue
        filtered_offers.append(offer)
    return filtered_offers


def simulate_order_choose(weights: List[float],
                          nicks: List[str],
                          maker_count: int,
                          bondless: float) -> List[str]:
    """
    Return list with the nicks of the selected offers.
    The order choosing algos are intended to be exactly the same as the JoinMarket ones.
    """
    chosen_nicks = []
    sum_weights = sum(weights)
    # Makes copies to keep the original intact
    sim_weights = weights[:]
    sim_nicks = nicks[:]
    for _ in range(maker_count):
        if random() >= bondless and sum_weights != 0:
            # Use fidelity_bond_weighted_order_choose
            nick_index = choices(range(len(sim_nicks)), sim_weights, k=1)[0]
        else:
            # Use random_under_max_order_choose
            nick_index = randrange(len(sim_nicks))
        chosen_nicks.append(sim_nicks[nick_index])
        sum_weights -= sim_weights.pop(nick_index)
        sim_nicks.pop(nick_index)

    return chosen_nicks


def simulate(weights: List[float], nicks: List[str], trials: int, sample_size: int, maker_count: int,
             bondless: float) -> Dict[str, List[float]]:
    """
    Simulate `sample_size` CoinJoins for `trials` times.
    Return a dict with key being the nick and value its corresponding results, one for trial.
    Each result represents times_picked / sample_size.
    """
    res: Dict[str, List[float]] = {nick: [] for nick in nicks}
    for _ in range(trials):
        trial_res = {nick: 0 for nick in nicks}
        for _ in range(sample_size):
            chosen_nicks = simulate_order_choose(weights, nicks, maker_count, bondless)
            for nick in chosen_nicks:
                trial_res[nick] += 1
        for nick in nicks:
            res[nick].append(trial_res[nick] / sample_size)
    return res


def main() -> None:
    args = get_args()
    log = get_logger(args.verbose)
    offers = args.orderbook["offers"]
    if args.amount is not None:
        log.info('Filtering by CoinJoin amount')
        prev_length = len(offers)
        offers = [offer for offer in args.orderbook["offers"] if offer["minsize"] <= args.amount <= offer["maxsize"]]
        log.info(f'Filtered {prev_length - len(offers)} offers')
    if args.max_fees is not None:
        prev_length = len(offers)
        log.info('Filtering by max fee')
        offers = filter_ob_by_fees(offers, args.max_fees[0], args.max_fees[1])
        log.info(f'Filtered {prev_length - len(offers)} offers')
    # Remove duplicate counterparties, for now ignore fees
    prev_length = len(offers)
    log.info('Removing duplicates')
    offers = {offer["counterparty"]: offer for offer in offers}
    log.info(f'Removed {prev_length - len(offers)} offers')
    offers_ = list(offers.values())
    values = [order["fidelity_bond_value"] for order in offers_]
    nicks = [order["counterparty"] for order in offers_]
    # Run simulation to find picking chances of each bond in the orderbook
    n_offers = len(offers)
    if n_offers < args.maker_count:
        log.error(f"Not enough offers in the orderbook ({n_offers}) "
                  f"to perform simulation with {args.maker_count} counterparties")
        sys.exit(ExitStatus.ARGERROR.value)
    sample_size = n_offers * 100 if args.sample_size is None else args.sample_size
    log.info(f"Running simulation for {args.trials} trials ({sample_size} CoinJoin each)...")
    start_time = monotonic()
    res = simulate(values, nicks, args.trials, sample_size, args.maker_count, args.bondless_allowance)
    log.info(f'Simulation completed in {monotonic() - start_time:.2f}s')
    log.info("Estimated picking chances (95% confidence):")
    sorted_orders = dict(sorted(offers.items(), key=lambda x: x[1]['fidelity_bond_value'], reverse=True))
    print('NICK (BOND VALUE)\n')
    for nick in sorted_orders:
        mean_res = mean(res[nick])
        stdev_res = stdev(res[nick]) * 1.96
        bond_value = float(Decimal(offers[nick]["fidelity_bond_value"]) / Decimal(1e16))
        print(
            f'{offers[nick]["counterparty"]} ({bond_value:.16f}): {mean_res:.3%} +/- {stdev_res:.3%}')


if __name__ == "__main__":
    main()
