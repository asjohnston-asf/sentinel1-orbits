import pytest
import responses
from botocore.stub import Stubber

import fetcher


@pytest.fixture
def s3_stubber():
    with Stubber(fetcher.s3) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


@responses.activate
def test_esa_token():
    url = fetcher.ESA_CREATE_TOKEN_URL
    request_payload = {
        'client_id': 'cdse-public',
        'grant_type': 'password',
        'username': 'myUsername',
        'password': 'myPassword',
    }
    response_payload = {'access_token': 'ABC123', 'session_state': 'mySessionId'}
    post_request = responses.post(
        url=url,
        match=[responses.matchers.urlencoded_params_matcher(request_payload)],
        json=response_payload,
    )

    url = f'{fetcher.ESA_DELETE_TOKEN_URL}/mySessionId'
    headers = {
        'Authorization': 'Bearer ABC123',
        'Content-Type': 'application/json',
    }
    delete_request = responses.delete(
        url=url,
        match=[responses.matchers.header_matcher(headers)],
    )

    with fetcher.EsaToken(username='myUsername', password='myPassword') as token:
        assert token == 'ABC123'

    assert post_request.call_count == 1
    assert delete_request.call_count == 1


def test_get_s3_orbits(s3_stubber):
    s3_stubber.add_response(
        method='list_objects_v2',
        expected_params={'Bucket': 'foo', 'Prefix': 'bar'},
        service_response={
            'Contents': [
                {'Key': 'bar/a'},
                {'Key': 'bar/stuff/e.txt'},
            ],
            'IsTruncated': True,
            'NextContinuationToken': 'token1',
        },
    )

    s3_stubber.add_response(
        method='list_objects_v2',
        expected_params={
            'Bucket': 'foo',
            'Prefix': 'bar',
            'ContinuationToken': 'token1',
        },
        service_response={
            'Contents': [
                {'Key': 'bar/c.zip'},
                {'Key': 'bar/hello/world/f'},
            ],
            'IsTruncated': True,
            'NextContinuationToken': 'token2',
        },
    )

    s3_stubber.add_response(
        method='list_objects_v2',
        expected_params={
            'Bucket': 'foo',
            'Prefix': 'bar',
            'ContinuationToken': 'token2',
        },
        service_response={},
    )

    assert fetcher.get_s3_orbits('foo', 'bar') == {'a', 'e.txt', 'c.zip', 'f'}


@responses.activate
def test_copy_file(s3_stubber):
    responses.get(
        url='https://zipper.dataspace.copernicus.eu/download/myId',
        match=[responses.matchers.header_matcher({'Authorization': 'Bearer myToken'})],
        body='foo',
    )
    s3_stubber.add_response(
        method='put_object',
        expected_params={
            'Bucket': 'myBucket',
            'Key': 'myOrbitType/myFilename',
            'Body': 'foo',
        },
        service_response={},
    )
    fetcher.copy_file('myFilename', 'myId', 'myToken', 'myBucket', 'myOrbitType')


@pytest.mark.network
@pytest.mark.parametrize('orbit_type', ['AUX_POEORB', 'AUX_RESORB'])
def test_get_cdse_orbits(orbit_type):
    orbits = fetcher.get_cdse_orbits(orbit_type)

    assert len(orbits)
    assert all('filename' in orbit and 'id' in orbit for orbit in orbits)

    # filename: S1A_OPER_AUX_POEORB_OPOD_20260122T070605_V20260101T225942_20260103T005942.EOF
    assert all(orbit_type in orbit['filename'] for orbit in orbits)
    assert all(orbit['filename'].endswith('.EOF') for orbit in orbits)
    # id: 4e25c9ba-a0ad-42ac-94da-9c66228c413b
    assert all(len(orbit['id']) == 36 for orbit in orbits)
