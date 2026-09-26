"""One identity for an exchange observation, whatever file format carried it (r5.10).

An observation is one security in one series on one session: (ISIN, series). The same key is used for
versioning, duplicate detection, withdrawal, the delivery join and quarantine matching.

r5.8-r5.9 keyed UDiFF rows by FinInstrmId and legacy rows by ISIN+series, so the same instrument on the same
date had two identities. A correction delivered in the other format was then a "first version" and got the
inferred trade-date availability: a price received days later was usable on the trade date (look-ahead), and
the canonical read failed with two candidates. FinInstrmId is kept as an attribute of the observation (the join
key to the MII security master); it no longer decides whether two rows are the same observation.

Within one file, the same FinInstrmId twice, or the same (ISIN, series) under two FinInstrmIds, is a duplicate
and is quarantined, never resolved by guessing.
"""


def observation_key(r):
    return (r.get("isin"), r.get("series"))
