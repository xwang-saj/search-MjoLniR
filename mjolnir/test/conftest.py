import findspark
findspark.init()  # must happen before importing pyspark

import hashlib  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
from pyspark import SparkContext, SparkConf  # noqa: E402
from pyspark.sql import HiveContext  # noqa: E402
import pytest  # noqa: E402
import requests  # noqa: E402
import sqlite3  # noqa: E402


def quiet_log4j():
    logger = logging.getLogger('py4j')
    logger.setLevel(logging.WARN)


@pytest.fixture(scope="session")
def spark_context(request):
    """Fixture for creating a spark context.

    Args:
        request: pytest.FixtureRequest object

    Returns:
        SparkContext for tests
    """

    # TODO: This is much too specialized to the vagrant test environment
    extraClassPath = '/vagrant/jvm/target/mjolnir-0.1-jar-with-dependencies.jar'
    quiet_log4j()
    conf = (
        SparkConf()
        .setMaster("local[2]")
        .setAppName("pytest-pyspark-local-testing")
        .set('spark.driver.extraClassPath', extraClassPath)
        .set('spark.executor.extraClassPath', extraClassPath))
    sc = SparkContext(conf=conf)
    yield sc
    sc.stop()


@pytest.fixture(scope="session")
def hive_context(spark_context):
    """Fixture for creating a Hive context.

    Args:
        spark_context: spark_context fixture

    Returns:
        HiveContext for tests
    """
    return HiveContext(spark_context)


@pytest.fixture()
def make_requests_session():
    def f(path):
        return MockSession(path)
    return f


class MockSession(object):
    def __init__(self, fixture_file):
        self._session = None
        if fixture_file[0] != '/':
            dir_path = os.path.dirname(os.path.realpath(__file__))
            fixture_file = os.path.join(dir_path, fixture_file)
        # Use sqlite for storage so we don't have to figure out how
        # multiple pyspark executors write to the same file
        self.sqlite = sqlite3.connect(fixture_file)
        self.sqlite.execute(
            "CREATE TABLE IF NOT EXISTS requests " +
            "(digest text PRIMARY KEY, status_code int, content text)")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def get(self, url, data=None):
        md5 = hashlib.md5()
        md5.update(url)
        md5.update(data)
        digest = md5.hexdigest()

        for row in self.sqlite.execute("SELECT status_code, content from requests WHERE digest=?", [digest]):
            return MockResponse(row[0], row[1])

        r = requests.get(url, data=data)

        try:
            self.sqlite.execute("INSERT INTO requests VALUES (?,?,?)", [digest, r.status_code, r.text])
            self.sqlite.commit()
        except sqlite3.IntegrityError:
            # inserted elsewhere? no big deal
            pass

        return MockResponse(r.status_code, r.text)


class MockResponse(object):
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text
