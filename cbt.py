#!/usr/bin/python3
import argparse
import collections
import logging
import pprint
import sys

import settings
import benchmarkfactory
from cluster.ceph import Ceph
from log_support import setup_loggers

logger = logging.getLogger("cbt")
# Uncomment this if further debug detail (module, funcname) are needed
# FORMAT = "%(asctime)s] [%(levelname)s] [%(name)s] [%(funcName)s():%(lineno)s] %(message)s"
# logging.basicConfig(format=FORMAT, force=True)
# logger.setLevel(logging.DEBUG)


def parse_args(args):
    parser = argparse.ArgumentParser(description="Continuously run ceph tests.")
    parser.add_argument(
        "-a",
        "--archive",
        required=True,
        help="Directory where the results should be archived.",
    )

    parser.add_argument(
        "-c",
        "--conf",
        required=False,
        help="The ceph.conf file to use.",
    )

    parser.add_argument(
        "config_file",
        help="YAML config file.",
    )

    return parser.parse_args(args[1:])


def main(argv):
    setup_loggers()
    ctx = parse_args(argv)
    settings.initialize(ctx)

    logger.debug(
        "Settings.cluster:\n    %s",
        pprint.pformat(settings.cluster).replace("\n", "\n    "),
    )

    global_init = collections.OrderedDict()
    rebuild_every_test = settings.cluster.get("rebuild_every_test", False)
    archive_dir = settings.cluster.get("archive_dir")

    logger.debug(
        "Rebuild every test: %s, Archive Dir: %s", rebuild_every_test, archive_dir
    )

    # FIXME: Create ClusterFactory and parametrically match benchmarks and clusters.
    cluster = Ceph(settings.cluster)

    logger.debug("Initialized cluster object: %s", cluster)

    # Only initialize and prefill upfront if we aren't rebuilding for each test.
    if not rebuild_every_test:
        if not cluster.use_existing:
            cluster.initialize()
        # Why does it need to iterate for the creation of benchmarks?
        for iteration in range(settings.cluster.get("iterations", 0)):
            logger.debug("Iteration: %d", iteration)
            benchmarks = benchmarkfactory.get_all(archive_dir, cluster, iteration)
            logger.debug("Benchmarks: %s", benchmarks)
            for b in benchmarks:
                if b.exists():
                    logger.debug(
                        "Benchmark %s already exists, skipping initialization.", b
                    )
                    continue
                if b.getclass() not in global_init:
                    logger.debug("Initializing Benchmark: %s", b)
                    b.initialize()
                    b.initialize_endpoints()
                    b.prefill()
                    b.cleanup()

                logger.debug("Benchmark %s initialized.", b)
                # Only initialize once per class.
                global_init[b.getclass()] = b

    logger.debug("Global initialization complete: %s", global_init)

    logger.debug("Read Test configuration: %s", settings.cluster.get("tests", []))
    # logger.debug("Settings.cluster.is_teuthology:%s",settings.cluster.get('is_teuthology', False))
    # Run the benchmarks
    return_code = 0
    try:
        for iteration in range(settings.cluster.get("iterations", 0)):
            benchmarks = benchmarkfactory.get_all(archive_dir, cluster, iteration)
            for b in benchmarks:
                if not b.exists() and not settings.cluster.get("is_teuthology", False):
                    continue

                if rebuild_every_test:
                    cluster.initialize()
                    b.initialize()
                # Always try to initialize endpoints before running the test
                b.initialize_endpoints()
                logger.info(f"Running benchmark %s == iteration %d ==" % (b, iteration))
                b.run()
    except:
        return_code = 1  # FAIL
        logger.exception("During tests")

    return return_code


if __name__ == "__main__":
    exit(main(sys.argv))
