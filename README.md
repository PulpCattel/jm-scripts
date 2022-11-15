# JoinMarket scripts

Standalone scripts for [JoinMarket](https://github.com/JoinMarket-Org/joinmarket-clientserver), strictly no dependencies.

Clone the repo or copy/paste the scripts.

Usage examples are below.

### Scripts

* [`jmfinder.py`](#jmfinder)
* [`jmsim.py`](#jmsim)

## jmfinder

```console
$ python3 jmfinder.py -h
usage: jmfinder.py [options] start [end]

Given a starting and finishing block height, finds JoinMarket CoinJoins.

positional arguments:
  start                 Start block height, pass a negative value to scan the last n blocks from end
  end                   End block height, default is the latest block

optional arguments:
  -h, --help            show this help message and exit
  -o HOST, --host HOST  Bitcoin Core REST host, default localhost
  -p PORT, --port PORT  Bitcoin Core REST port, default 8332
  -f CANDIDATE_FILE_NAME, --filename CANDIDATE_FILE_NAME
                        Filename to write identifiers of candidate transactions, default candidates.txt
  -j N, --jobs N        Use N processes, default to the number of processors on the machine. Pass 0 to prevent multiprocessing
  -v, --verbose         Increase logging verbosity to DEBUG
```

### Description

This is a much faster version of [`snicker-finder.py`](https://github.com/JoinMarket-Org/joinmarket-clientserver/blob/master/scripts/snicker/snicker-finder.py) from the JoinMarket repo.
If you are familiar with it, you can call `jmfinder.py` in the exact same way.

The identifiers saved on disk are in `csv` format, as follows:

`TXID,height,index`

Where:
* `TXID` is the txid of the Bitcoin transaction
* `height` is the block height where the transaction is found
* `index` is the position of the transaction in the block. Index 0 means the first transaction in the block.

### Requirements

The only requirement is a Bitcoin Core node running with [REST interface](https://github.com/bitcoin/bitcoin/blob/master/doc/REST-interface.md) enabled.
Pass `-rest` through CLI or set `rest=1` in `bitcoin.conf`

### Example

```console
$ python3 jmfinder.py -19
11/10/2022 07:48:20 INFO: Scanning from block 762603 to block 762621
11/10/2022 07:48:20 INFO: 

Found possible JoinMarket CoinJoin at height 762603
TXID: 9ec228c59033f7111f49a5b9f14ce364af931700578b2a9a32cf1b6cc517e367
Inputs: 18
Outputs: 16
Equal value outputs: 8
Equal output amount: 31594374
Vsize: 1729
Version: 2
Locktime: 3674210303

11/10/2022 07:48:20 INFO: Processed block 762603.
11/10/2022 07:48:20 INFO: Processed block 762604.
11/10/2022 07:48:20 INFO: Processed block 762605.
11/10/2022 07:48:20 INFO: Processed block 762606.
11/10/2022 07:48:20 INFO: Processed block 762607.
11/10/2022 07:48:21 INFO: Processed block 762608.
11/10/2022 07:48:21 INFO: Processed block 762609.
11/10/2022 07:48:21 INFO: 

Found possible JoinMarket CoinJoin at height 762610
TXID: 1269e297e323607f10dc32a0f30f84509fa43a208bf76a3e7bcea67350a721f1
Inputs: 5
Outputs: 7
Equal value outputs: 4
Equal output amount: 100262
Vsize: 628
Version: 1
Locktime: 3479639216

11/10/2022 07:48:21 INFO: Processed block 762610.
11/10/2022 07:48:21 INFO: Processed block 762611.
11/10/2022 07:48:21 INFO: Processed block 762612.
11/10/2022 07:48:21 INFO: Processed block 762613.
11/10/2022 07:48:21 INFO: Processed block 762614.
11/10/2022 07:48:21 INFO: Processed block 762615.
11/10/2022 07:48:21 INFO: Processed block 762616.
11/10/2022 07:48:21 INFO: Processed block 762617.
11/10/2022 07:48:21 INFO: Processed block 762618.
11/10/2022 07:48:21 INFO: Processed block 762619.
11/10/2022 07:48:21 INFO: Processed block 762620.
11/10/2022 07:48:22 INFO: Processed block 762621.
11/10/2022 07:48:22 INFO: Scan completed in 0.80s
```

---

## jmsim

```console
$ python3 jmsim.py -h
usage: jmsim.py [options] orderbook

Given an orderbook file as JSON, e.g., exported from ob-watcher.py, run multiple CoinJoin simulations to estimate the picking chances of each maker offer.

positional arguments:
  orderbook             Path to the exported orderbook in JSON format

optional arguments:
  -h, --help            show this help message and exit
  -n MAKER_COUNT, --maker-count MAKER_COUNT
                        Number of counterparties to use in CoinJoin simulation, default 10
  -t TRIALS, --trials TRIALS
                        Number of trials to estimate picking chances, default 10
  -s SAMPLE_SIZE, --sample_size SAMPLE_SIZE
                        Number of CoinJoin simulations for each trial, default 100 times the number of (filtered) offers in the orderbook
  -b BONDLESS_ALLOWANCE, --bondless BONDLESS_ALLOWANCE
                        Bondless allowance to use for CoinJoin simulation (instead of bondless_makers_allowance default, 0.125)
  -a AMOUNT, --amount AMOUNT
                        Filter orderbook based on CoinJoin amount in sats. If an offer can't satisfy this amount, it's disregarded. Default does not filter
  -f MAX_FEES, --max-fees MAX_FEES
                        Filter the orderbook based on maximum fees asked (naively, does not take into account the CoinJoin amount). Specify both absolute and relative fees comma separated,
                        e.g., 1000,0.002 (default does not filter)
  -v, --verbose         Increase logging verbosity to DEBUG
```

### Description

This is a simple script to run CoinJoin simulations against a given JoinMarket orderbook.
It emulates the JoinMarket order choosing algorithm to find out how often each maker offer gets selected by a taker.

The only thing you need is an orderbook file in JSON format.
To get that:
* Run the [ob-watcher.py](https://github.com/JoinMarket-Org/joinmarket-clientserver/blob/master/docs/orderbook.md) script yourself and export it from there.
* Find a public orderbook you trust and export it from there.
* For testing, you can build the JSON file yourself, ideally a script should be made to make it trivial.

### Requirements
None.

### Example
```console
$ python3 jmsim.py orderbook.json -f 1000,0.4 -a 120000
11/11/2022 01:09:30 INFO: Filtering by CoinJoin amount
11/11/2022 01:09:30 INFO: Filtered 49 offers
11/11/2022 01:09:30 INFO: Filtering by max fee
11/11/2022 01:09:30 INFO: Filtered 3 offers
11/11/2022 01:09:30 INFO: Removing duplicates
11/11/2022 01:09:30 INFO: Removed 0 offers
11/11/2022 01:09:30 INFO: Running simulation for 10 trials (12700 CoinJoin each)...
11/11/2022 01:09:35 INFO: Simulation completed in 5.64s
11/11/2022 01:09:35 INFO: Estimated picking chance (95% confidence):
NICK (BOND VALUE)

J53Aha9gj4w96Vqi (0.0000060668286756): 98.575% +/- 0.242%
J58KVQjJf2PmTzH2 (0.0000052877962973): 97.959% +/- 0.291%
J58rG3xDWFHTYKNY (0.0000046284301680): 97.130% +/- 0.194%
J52E94aXXb45Camt (0.0000034399835598): 94.490% +/- 0.394%
J5E8TeyyqboMf7ZV (0.0000020544660432): 85.795% +/- 0.780%
J56SJcw5RqqoCunu (0.0000015965753131): 79.414% +/- 0.632%
J5BYzMJBJcj7pJnC (0.0000015824203924): 79.160% +/- 0.808%
J5UcuygR4cGkFnPO (0.0000011940295909): 70.487% +/- 0.945%
J57P4drm3eDqQrP6 (0.0000009053333157): 60.719% +/- 0.941%
J58GLDmebggitTug (0.0000008570142480): 59.058% +/- 0.389%
J5DjhUAQDV5f6oky (0.0000008007055591): 56.783% +/- 0.860%
J5DKuNtXsUYQuKQM (0.0000000079889032): 1.789% +/- 0.225%
J58tmdiZSmCoZtWa (0.0000000043598671): 1.422% +/- 0.205%
J52HViFEn3UEWU37 (0.0000000032181691): 1.361% +/- 0.203%
J56x6miKTQrUHa3N (0.0000000031051122): 1.272% +/- 0.198%
J54tHpQVyy1yGtTb (0.0000000023373594): 1.181% +/- 0.177%
J57owrVxdx8P4RcP (0.0000000019626523): 1.161% +/- 0.266%
J569vKm6fGYbBv8K (0.0000000012052017): 1.104% +/- 0.219%
J5EAZtxNavsHF6aS (0.0000000009622733): 1.071% +/- 0.165%
J5C4RjsXXRAQoDDP (0.0000000007775088): 1.024% +/- 0.136%
J55eNmqmEcMw72wi (0.0000000001026433): 1.032% +/- 0.192%
J58BYuKYDwSWThkC (0.0000000000798477): 1.033% +/- 0.146%
J58FYTdN71rkWGZZ (0.0000000000444969): 1.046% +/- 0.142%
J5B6AqVatJo57p4R (0.0000000000027347): 1.015% +/- 0.160%
J57BzkF37C7MDiMn (0.0000000000009492): 1.022% +/- 0.141%
J5A32Za2RHEYtCKk (0.0000000000000000): 1.029% +/- 0.152%
J5DawQxjcQzUrVAU (0.0000000000000000): 1.033% +/- 0.179%
J5C42iJ8gvvVUKqq (0.0000000000000000): 1.052% +/- 0.178%
J5BjH1zdiRWnE45t (0.0000000000000000): 0.980% +/- 0.106%
J5Ee8uoQVCsxHSj2 (0.0000000000000000): 1.029% +/- 0.178%
J535PB6RKE3CF3Dz (0.0000000000000000): 1.012% +/- 0.220%
[...]
```

---

Enjoy!
