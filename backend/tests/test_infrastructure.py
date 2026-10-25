"""These checks deliberately require the real PostGIS/Redis development stack."""
import uuid

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from redis import Redis

from flowgic.celery import app


@pytest.mark.integration
def test_postgis_backend_and_extension(db):
    assert connection.settings_dict['ENGINE'] == 'django.contrib.gis.db.backends.postgis'
    assert connection.pg_version // 10000 == 16
    with connection.cursor() as cursor:
        cursor.execute("SELECT PostGIS_Version(), ST_AsText(ST_SetSRID(ST_MakePoint(92.87, 56.01), 4326))")
        version, point = cursor.fetchone()
        assert version.startswith('3.4')
        assert point == 'POINT(92.87 56.01)'
        cursor.execute('SELECT rolsuper FROM pg_roles WHERE rolname = current_user')
        assert cursor.fetchone() == (False,)


@pytest.mark.integration
def test_redis_cache_round_trip():
    key = f'infrastructure-check-{uuid.uuid4()}'
    try:
        cache.set(key, {'ready': True}, timeout=30)
        assert cache.get(key) == {'ready': True}
    finally:
        cache.delete(key)


@pytest.mark.integration
def test_celery_redis_connections():
    assert app.conf.broker_url == settings.CELERY_BROKER_URL
    assert app.conf.result_backend == settings.CELERY_RESULT_BACKEND
    for url in (app.conf.broker_url, app.conf.result_backend):
        with Redis.from_url(url) as client:
            assert client.ping()
