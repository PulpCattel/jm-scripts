#!/usr/bin/env python3
"""
Standalone script with no dependencies.
The only requirement is a Bitcoin Core node running with REST server enabled.
Pass -rest through CLI or rest=1 in bitcoin.conf
The node can be pruned and txindex is not required because jmfinder scans the blocks directly.

Most of the raw data parsing code is taken from https://github.com/alecalve/python-bitcoin-blockchain-parser
Thank you!
"""
import hashlib
import json
import struct
import sys
from argparse import ArgumentParser, Namespace
from collections import Counter
from enum import Enum
from logging import Logger, getLogger, Formatter, StreamHandler
from math import ceil
from time import monotonic
from typing import Tuple, Dict, Any, List
from urllib.error import URLError, HTTPError
from urllib.request import urlopen, Request

DESCRIPTION = """
Given a starting and finishing block height, finds JoinMarket CoinJoins.
"""

# JOINMARKET PATTERN
# Number inputs >= number of CoinJoin outs (equal sized)
# Non-equal outs = CoinJoin outs or CoinJoin outs -1
# At least 3 CoinJoin outs (2 technically possible but excluded)
# We filter out joins with less than 3 participants as they are
# not really in JoinMarket "correct usage" and there will be a lot
# of false positives.
# We filter out "joins" less than 75000 sats as they are unlikely to
# be JoinMarket and there tend to be many low-value false positives.
MIN_PARTICIPANTS = 3
MIN_CJ_AMOUNT = 75000


def is_jm(n_in: int, n_out: int, values: List[int]) -> Tuple[int, int]:
    """
    Check JoinMarket pattern.
    Return a tuple with the CoinJoin amount and the number of equal outputs.
    These are 0,0 if not a JoinMarket CoinJoin.
    """
    assumed_cj_outs = n_out // 2
    if n_out % 2:
        assumed_cj_outs += 1
    if assumed_cj_outs < MIN_PARTICIPANTS:
        return 0, 0
    if n_in < assumed_cj_outs:
        return 0, 0
    most_common_value, equal_outs = Counter(values).most_common(1)[0]
    if most_common_value < MIN_CJ_AMOUNT:
        return 0, 0
    if equal_outs != assumed_cj_outs:
        return 0, 0
    return most_common_value, equal_outs


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


def get_args() -> Namespace:
    parser = ArgumentParser(
        usage="jmfinder.py [options] start [end]",
        description=DESCRIPTION,
    )
    parser.add_argument(
        "start",
        action="store",
        type=int,
        help="Start block height, pass a negative value to scan the last n blocks from end",
    )
    parser.add_argument(
        "end",
        nargs='?',
        action="store",
        type=int,
        help="End block height, default is the latest block",
        default=0
    )
    parser.add_argument(
        "-o",
        '--host',
        action="store",
        type=str,
        help="Bitcoin Core REST host, default localhost",
        default='localhost'
    )
    parser.add_argument(
        "-p",
        '--port',
        action="store",
        type=int,
        help="Bitcoin Core REST port, default 8332",
        default=8332
    )
    parser.add_argument(
        '-f',
        '--filename',
        action='store',
        type=str,
        dest='candidate_file_name',
        help='Filename to write identifiers of candidate '
             'transactions, default candidates.txt',
        default='candidates.txt')
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help="Increase logging verbosity to DEBUG",
    )
    return parser.parse_args()


class ExitStatus(Enum):
    """
    Exit status codes.
    """
    SUCCESS = 0
    FAILURE = 1
    ARGERROR = 2


class ReqType(Enum):
    """
    Possible request types of the REST interface.
    """
    BIN = ".bin"
    HEX = ".hex"
    JSON = ".json"


class RestApi(Enum):
    """
    Bitcoin Core supported REST API.
    """

    # Given a transaction hash, return a transaction.
    # By default, this method will only search the mempool. To query for a confirmed transaction,
    # enable the transaction index via "txindex=1" command line/configuration option.
    TX = '/tx'
    # Given a block hash, return a block
    BLOCK = '/block'
    # Given a block hash, return a block only containing the TXID
    # instead of the complete transaction details
    BLOCK_NO_DETAILS = '/block/notxdetails'
    # Given a count and a block hash, return amount of block headers in upward direction
    HEADERS = '/headers'
    # Given a height, return hash of block at height provided
    BLOCKHASH = '/blockhashbyheight'
    # Return various state info regarding block chain processing
    # ONLY SUPPORTS JSON FORMAT
    CHAININFO = '/chaininfo'
    # Query UTXO set given a set of outpoints
    UTXO = '/getutxos'
    # Query UTXO set given a set of outpoint and apply mempool transactions during the calculation,
    # thus exposing their UTXOs and removing outputs that they spend
    UTXO_CHECK_MEMPOOL = '/getutxos/checkmempool'
    # Return various information about the mempool
    MEMPOOL_INFO = '/mempool/info'
    # Return transactions in the mempool
    MEMPOOL_CONTENT = '/mempool/contents'

    def to_uri(self, req_type: ReqType, *args) -> str:
        """
        Return complete URI for RestApi.
        """
        return f"{self.value}{''.join(f'/{arg}' for arg in args)}{req_type.value}"


class Btc:
    """
    Client object to interact with REST interface.
    """

    __slots__ = ('url', 'log')

    HEADERS = {'User-Agent': 'jmfinder'}
    TIMEOUT = 3

    def __init__(self, host: str, port: int, log: Logger):
        self.url = f'http://{host}:{port}'
        self.log = log

    def get_response(self, method: RestApi, *args, req_type: ReqType = ReqType.JSON) -> bytes:
        """
        Send HTTP request to the server.
        If the call succeeds, return raw response in bytes.
        Else log error and terminate the script, the "rationale" for this is below.
        """
        url = f'{self.url}/rest{method.to_uri(req_type, *args)}'
        request = Request(url, headers=self.HEADERS)
        try:
            with urlopen(request, timeout=self.TIMEOUT) as response:
                return response.read()
        except HTTPError as exc:
            self.log.error(f'Bad status code: {exc.code} {exc.reason}')
        except URLError as exc:
            self.log.error(f'Unable to connect to {url}: {exc.reason}')
        except TimeoutError:
            self.log.error('Request timed out')
        except Exception as exc:
            self.log.error(str(exc))
        self.log.error(f'Request for {url} failed')
        # Failed to perform HTTP request.
        # Since this is a standalone script, we are okay stopping the program here.
        # Ideally this could be improved so that's done somewhere else.
        # Also some re-try logic could be added in some cases.
        sys.exit(ExitStatus.FAILURE.value)

    def get_json(self, method: RestApi, *args) -> Dict[str, Any]:
        """
        Return the response body converted to Dict.
        """
        return json.loads(self.get_response(method, *args, req_type=ReqType.JSON))

    def get_block(self, blockhash: str, no_details: bool = False) -> Dict[str, Any]:
        """
        Wrapper around Block or BlockNoDetails method
        """
        return self.get_json(RestApi.BLOCK_NO_DETAILS if no_details else RestApi.BLOCK, blockhash)

    def get_blockhash(self, height: int) -> str:
        """
        Wrapper around Blockhash method
        """
        blockhash: str = (self.get_json(RestApi.BLOCKHASH, height))['blockhash']
        return blockhash

    def get_info(self) -> Dict[str, Any]:
        """
        Wrapper around Chaininfo method
        """
        return self.get_json(RestApi.CHAININFO)


def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def format_hash(hash_: bytes) -> str:
    return hash_[::-1].hex()


def decode_uint32(data: bytes) -> int:
    if len(data) != 4:
        raise ValueError
    return struct.unpack("<I", data)[0]


def decode_uint64(data: bytes) -> int:
    if len(data) != 8:
        raise ValueError
    return struct.unpack("<Q", data)[0]


def decode_varint(data: bytes) -> Tuple[int, int]:
    size = int(data[0])
    if size > 255:
        raise ValueError
    if size < 253:
        return size, 1
    if size == 253:
        format_ = '<H'
    elif size == 254:
        format_ = '<I'
    elif size == 255:
        format_ = '<Q'
    else:
        # Should never be reached
        raise ValueError(f"Unknown format for size : {size}")
    size = struct.calcsize(format_)
    return struct.unpack(format_, data[1:size + 1])[0], size + 1


def main() -> None:
    args = get_args()
    log = get_logger(args.verbose)
    btc = Btc(args.host, args.port, log)
    log.debug(f'Started HTTP client to {btc.url}')
    info = btc.get_info()
    end_block = args.end if args.end else info['blocks']
    if args.start < 0:
        start_block = end_block - abs(args.start) + 1
    else:
        start_block = args.start
    if info['pruned']:
        if start_block < info['pruneheight']:
            log.error(f"Can't scan past pruned height. Given start height ({start_block}) is lower than "
                      f"lowest-height complete block stored ({info['pruneheight']}).")
            sys.exit(ExitStatus.ARGERROR.value)
    log.info(f'Scanning from block {start_block} to block {end_block}')
    start_time = monotonic()
    results = []
    for height in range(start_block, end_block + 1):
        processed_txs = 0
        blockhash = btc.get_blockhash(height)
        # Get block in raw hex format
        block = btc.get_response(RestApi.BLOCK, blockhash, req_type=ReqType.BIN)

        # Parse block

        # Skip the header
        txs_data = block[80:]

        # The number of transactions contained in this block
        n_txs, block_offset = decode_varint(txs_data)

        # Loop through the block's transactions
        for i in range(n_txs):
            tx_size = 0
            # Try from 1024 (1KiB) -> 1073741824 (1GiB) slice widths
            for j in range(0, 20):
                try:
                    # Parse tx

                    offset_e = block_offset + (1024 * 2 ** j)
                    tx = txs_data[block_offset:offset_e]
                    # The transaction's version number
                    version = decode_uint32(tx[:4])
                    # The transaction's locktime as int
                    locktime = decode_uint32(tx[-4:])

                    is_segwit = False

                    tx_offset = 4

                    # Adds basic support for segwit transactions
                    #   - https://bitcoincore.org/en/segwit_wallet_dev/
                    #   - https://en.bitcoin.it/wiki/Protocol_documentation#BlockTransactions
                    if tx[tx_offset:tx_offset + 2] == b'\x00\x01':
                        is_segwit = True
                        tx_offset += 2

                    n_in, varint_size = decode_varint(tx[tx_offset:])
                    tx_offset += varint_size

                    # Parse inputs

                    for _ in range(n_in):
                        tx_input = tx[tx_offset:]
                        script_length, varint_length = decode_varint(tx_input[36:])
                        script_start = 36 + varint_length
                        in_size = script_start + script_length + 4
                        tx_offset += in_size

                    n_out, varint_size = decode_varint(tx[tx_offset:])
                    tx_offset += varint_size

                    # Parse outputs

                    values = []
                    for _ in range(n_out):
                        tx_output = tx[tx_offset:]
                        _value_hex = tx_output[:8]
                        # The value of the output expressed in sats
                        values.append(decode_uint64(_value_hex))
                        script_length, varint_size = decode_varint(tx_output[8:])
                        script_start = 8 + varint_size
                        out_size = script_start + script_length
                        tx_offset += out_size

                    # Parse witnesses

                    if is_segwit:
                        offset_before_tx_witnesses = tx_offset
                        for _ in range(n_in):
                            tx_witnesses_n, varint_size = decode_varint(tx[tx_offset:])
                            tx_offset += varint_size
                            for _ in range(tx_witnesses_n):
                                component_length, varint_size = decode_varint(tx[tx_offset:])
                                tx_offset += varint_size
                                tx_offset += component_length

                    tx_size = tx_offset + 4
                    tx = tx[:tx_size]
                    if tx_size != len(tx):
                        raise ValueError("Incomplete transaction")

                    # Segwit transactions have two transaction ids/hashes, txid and wtxid
                    # txid is a hash of all of the legacy transaction fields only
                    if is_segwit:
                        txid_data = tx[:4] + tx[6:offset_before_tx_witnesses] + tx[-4:]
                    else:
                        txid_data = tx
                    txid = format_hash(double_sha256(txid_data))

                    # The transaction size in virtual bytes.
                    if not is_segwit:
                        vsize = tx_size
                    else:
                        # The witness is the last element in a transaction before the
                        # 4 byte locktime and self._offset_before_tx_witnesses is the
                        # position where the witness starts
                        witness_size = tx_size - offset_before_tx_witnesses - 4

                        # sSze of the transaction without the segwit marker (2 bytes) and
                        # the witness
                        stripped_size = tx_size - (2 + witness_size)
                        weight = stripped_size * 3 + tx_size

                        # Vsize is weight / 4 rounded up
                        vsize = ceil(weight / 4)

                    # Check for JoinMarket pattern
                    most_common_value, equal_outs = is_jm(n_in, n_out, values)
                    if most_common_value > 0:
                        results.append(f'{txid},{height},{i}')
                        log.info(f'\n\nFound possible JoinMarket CoinJoin at height {height}\n'
                                 f'TXID: {txid}\n'
                                 f'Inputs: {n_in}\n'
                                 f'Outputs: {n_out}\n'
                                 f'Equal value outputs: {equal_outs}\n'
                                 f'Equal output amount: {most_common_value}\n'
                                 f'Vsize: {vsize}\n'
                                 f'Version: {version}\n'
                                 f'Locktime: {locktime}\n')
                    processed_txs += 1
                    break

                except Exception as exc:
                    # raise exc
                    continue

            # Skipping to the next transaction
            block_offset += tx_size

        # Make sure we have parsed all the transactions in the block
        if processed_txs != n_txs:
            log.error(f'Failed to parse {n_txs - processed_txs} transactions in block at height {height}')
            sys.exit(ExitStatus.FAILURE.value)
        log.info(f'Processed block {height}.')

    log.info(f'Scan completed in {monotonic() - start_time:.2f}s')
    with open(args.candidate_file_name, 'a+', encoding='UTF-8') as f:
        # Go to the beginning of the file
        f.seek(0)
        lines = [line.strip() for line in f.readlines()] + results
        # Remove duplicates and sort by block height
        result = sorted(set(lines), key=lambda x: x.split(',')[1])
        # Clear the old content
        f.truncate(0)
        f.writelines('\n'.join(result))


if __name__ == "__main__":
    main()
