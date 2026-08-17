#!/usr/bin/env python3
"""
Tests for the voice preview endpoint (POST /api/voice-preview).

Runnable directly, with no test runner and no network access:

    python tests/test_voice_preview.py

Edge TTS is never contacted: `app.generate_mp3_sync` is replaced by a fake that
writes deterministic bytes and records every invocation, which is exactly what
lets us assert that the cache and the per-voice lock prevent duplicate work.
"""

import os
import re
import sys
import shutil
import tempfile
import threading
import time
import traceback

# Import app.py and voices.py from the process working directory (the project
# root this file is meant to be run from). Deliberately not derived from
# __file__: the test runner may copy this file elsewhere, so the directory next
# to it is not a reliable pointer to the project.
sys.path.insert(0, os.getcwd())

import app as app_module  # noqa: E402
import voices  # noqa: E402

flask_app = app_module.app

PREVIEW_URL_RE = re.compile(r'^/api/voice-preview/preview_[0-9a-f]{32}\.mp3$')
CSRF_META_RE = re.compile(r'<meta name="csrf-token" content="([^"]+)"')

VALID_VOICE = "es-ES-AlvaroNeural"
OTHER_VALID_VOICE = "es-MX-JorgeNeural"
DALIA_VOICE = "es-MX-DaliaNeural"
ARBITRARY_VOICE = "es-XX-NoExisteNeural"

# Confirmed by a real edge_tts.list_voices() run: these are the only es-MX
# voices Microsoft offers.
MEXICAN_CATALOG = {
    "es-MX-DaliaNeural": "🇲🇽 Dalia (México)",
    "es-MX-JorgeNeural": "🇲🇽 Jorge (México)",
}

# Requested but absent from that run, so they are not part of the catalog.
DISCARDED_MEXICAN_VOICES = ("es-MX-CecilioNeural", "es-MX-BeatrizNeural")


# --------------------------------------------------------------------------
# Fake Edge TTS
# --------------------------------------------------------------------------

class FakeEdgeTTS:
    """Stand-in for utils.generate_mp3_sync. No network, no edge-tts."""

    def __init__(self, delay=0.0):
        self.delay = delay
        self.calls = []
        self._lock = threading.Lock()

    def __call__(self, text, voice, rate, pitch, volume, output_path):
        with self._lock:
            self.calls.append({
                'text': text,
                'voice': voice,
                'rate': rate,
                'pitch': pitch,
                'volume': volume,
                'output_path': output_path,
            })
        if self.delay:
            time.sleep(self.delay)
        with open(output_path, 'wb') as handle:
            handle.write(b'ID3-FAKE-MP3-' + voice.encode('utf-8'))

    @property
    def count(self):
        with self._lock:
            return len(self.calls)


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------

TMP_ROOT = None


def setup_module_dirs():
    global TMP_ROOT
    TMP_ROOT = tempfile.mkdtemp(prefix='tts_preview_tests_')
    flask_app.config.update(
        TESTING=True,
        PREVIEW_FOLDER=os.path.join(TMP_ROOT, 'previews'),
        GENERATED_FOLDER=os.path.join(TMP_ROOT, 'generated'),
        UPLOAD_FOLDER=os.path.join(TMP_ROOT, 'uploads'),
        PREVIEW_MAX_AGE_SECONDS=24 * 3600,
        RATELIMIT_ENABLED=False,
    )
    # Flask-Limiter caches the flag at init time, so disable the instance too.
    app_module.limiter.enabled = False
    for key in ('PREVIEW_FOLDER', 'GENERATED_FOLDER', 'UPLOAD_FOLDER'):
        os.makedirs(flask_app.config[key], exist_ok=True)


def teardown_module_dirs():
    if TMP_ROOT and os.path.isdir(TMP_ROOT):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)


def reset_state():
    """Empty the cache folders and forget the per-voice locks between tests."""
    for key in ('PREVIEW_FOLDER', 'GENERATED_FOLDER', 'UPLOAD_FOLDER'):
        folder = flask_app.config[key]
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder, exist_ok=True)
    with app_module._preview_locks_guard:
        app_module._preview_locks.clear()


def new_client():
    """Test client with a live session and its matching CSRF token."""
    client = flask_app.test_client()
    page = client.get('/')
    assert page.status_code == 200, f"GET / returned {page.status_code}"
    match = CSRF_META_RE.search(page.get_data(as_text=True))
    assert match, "No csrf-token meta tag found in the rendered page"
    return client, match.group(1)


def post_preview(client, token, payload, send_token=True, as_json=True):
    headers = {'X-CSRFToken': token} if send_token else {}
    if as_json:
        return client.post('/api/voice-preview', json=payload, headers=headers)
    headers['Content-Type'] = 'application/json'
    return client.post('/api/voice-preview', data=payload, headers=headers)


def preview_files():
    folder = flask_app.config['PREVIEW_FOLDER']
    return sorted(f for f in os.listdir(folder) if not f.startswith('.'))


def generated_files():
    folder = flask_app.config['GENERATED_FOLDER']
    return sorted(f for f in os.listdir(folder) if not f.startswith('.'))


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_valid_voice_generates_and_serves_preview():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake

    client, token = new_client()
    response = post_preview(client, token, {'voice': VALID_VOICE})

    assert response.status_code == 200, f"expected 200, got {response.status_code}: {response.get_data(as_text=True)}"
    body = response.get_json()
    assert body['success'] is True
    assert body['voice'] == VALID_VOICE
    assert body['cached'] is False
    assert PREVIEW_URL_RE.match(body['audio_url']), f"unexpected audio_url: {body['audio_url']}"

    assert fake.count == 1, f"expected 1 generation, got {fake.count}"
    assert len(preview_files()) == 1, f"expected 1 cached preview, got {preview_files()}"

    served = client.get(body['audio_url'])
    assert served.status_code == 200, f"serving preview returned {served.status_code}"
    assert served.get_data() == b'ID3-FAKE-MP3-' + VALID_VOICE.encode('utf-8')


def test_arbitrary_voice_is_rejected():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake
    client, token = new_client()

    rejected_payloads = [
        {'voice': ARBITRARY_VOICE},           # not in the catalog
        {'voice': 'es-MX-CecilioNeural'},     # discarded: does not exist in edge-tts
        {'voice': 'es-MX-BeatrizNeural'},     # discarded: does not exist in edge-tts
        {'voice': ''},                        # empty
        {'voice': None},                      # null
        {},                                   # missing field
        {'voice': ['es-ES-AlvaroNeural']},    # wrong type
    ]
    for payload in rejected_payloads:
        response = post_preview(client, token, payload)
        assert response.status_code == 400, (
            f"payload {payload!r} should be rejected with 400, got {response.status_code}"
        )
        assert 'error' in response.get_json()

    # Non-JSON body is rejected too.
    response = post_preview(client, token, 'not json at all', as_json=False)
    assert response.status_code == 400, f"non-JSON body should be 400, got {response.status_code}"

    assert fake.count == 0, "a rejected voice must never reach the TTS engine"
    assert preview_files() == [], f"no file should be created, found {preview_files()}"


def test_csrf_is_required():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake
    client, token = new_client()

    response = post_preview(client, token, {'voice': VALID_VOICE}, send_token=False)
    assert response.status_code == 400, f"missing CSRF token should be 400, got {response.status_code}"
    assert fake.count == 0, "a CSRF-rejected request must never reach the TTS engine"


def test_fixed_preview_text_and_parameters():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake
    client, token = new_client()

    # Any attempt to smuggle text or parameters in is ignored.
    response = post_preview(client, token, {
        'voice': VALID_VOICE,
        'text': 'TEXTO INYECTADO POR EL CLIENTE',
        'text_content': 'OTRO TEXTO',
        'rate': 50,
        'pitch': 15,
        'volume': 40,
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    assert fake.count == 1

    call = fake.calls[0]
    assert call['text'] == voices.PREVIEW_TEXT, f"unexpected preview text: {call['text']!r}"
    assert call['text'] == "Hola. Esta es una muestra de mi voz. Espero que te guste cómo sueno."
    assert call['voice'] == VALID_VOICE
    assert (call['rate'], call['pitch'], call['volume']) == (0, 0, 0), (
        f"preview parameters must stay fixed, got {call['rate']}/{call['pitch']}/{call['volume']}"
    )


def test_second_request_is_served_from_cache():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake
    client, token = new_client()

    first = post_preview(client, token, {'voice': VALID_VOICE}).get_json()
    second = post_preview(client, token, {'voice': VALID_VOICE}).get_json()

    assert first['audio_url'] == second['audio_url'], "cache key must be deterministic"
    assert first['cached'] is False and second['cached'] is True
    assert fake.count == 1, f"cached request regenerated the clip ({fake.count} calls)"

    # A different voice is a different cache entry.
    third = post_preview(client, token, {'voice': OTHER_VALID_VOICE}).get_json()
    assert third['audio_url'] != first['audio_url']
    assert fake.count == 2, f"expected 2 generations in total, got {fake.count}"


def test_concurrent_requests_generate_once():
    # A slow fake guarantees the second request arrives while the first is
    # still inside the per-voice lock.
    fake = FakeEdgeTTS(delay=0.6)
    app_module.generate_mp3_sync = fake

    barrier = threading.Barrier(3)
    results = {}
    errors = []

    def worker(index):
        try:
            client, token = new_client()
            barrier.wait(timeout=10)
            response = post_preview(client, token, {'voice': VALID_VOICE})
            results[index] = (response.status_code, response.get_json())
        except Exception:  # pragma: no cover - surfaced by the assertion below
            errors.append(traceback.format_exc())
            try:
                barrier.abort()
            except Exception:
                pass

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, "worker thread failed:\n" + "\n".join(errors)
    assert len(results) == 2, f"expected 2 responses, got {results}"

    statuses = {status for status, _ in results.values()}
    assert statuses == {200}, f"concurrent requests returned {statuses}"

    urls = {body['audio_url'] for _, body in results.values()}
    assert len(urls) == 1, f"concurrent requests returned different URLs: {urls}"

    assert fake.count == 1, f"race condition: clip generated {fake.count} times instead of 1"
    assert len(preview_files()) == 1, f"expected a single cached file, got {preview_files()}"


def test_preview_is_separate_from_main_audio():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake
    client, token = new_client()

    # 1. A preview writes only into PREVIEW_FOLDER.
    preview_body = post_preview(client, token, {'voice': VALID_VOICE}).get_json()
    assert len(preview_files()) == 1
    assert generated_files() == [], f"preview leaked into GENERATED_FOLDER: {generated_files()}"

    # 2. A normal generation writes only into GENERATED_FOLDER.
    generate_response = client.post(
        '/api/generate',
        data={'text_content': 'Texto normal del usuario', 'voice': VALID_VOICE},
        headers={'X-CSRFToken': token},
        content_type='multipart/form-data',
    )
    assert generate_response.status_code == 200, generate_response.get_data(as_text=True)
    generate_body = generate_response.get_json()

    assert len(generated_files()) == 1, f"expected 1 generated file, got {generated_files()}"
    assert len(preview_files()) == 1, "normal generation must not touch the preview cache"
    assert not generate_body['audio_url'].startswith('/api/voice-preview')
    assert generate_body['audio_url'] != preview_body['audio_url']

    # 3. The generated clip used the user's text, not the preview sentence.
    generation_call = fake.calls[-1]
    assert generation_call['text'].strip() == 'Texto normal del usuario'
    assert generation_call['text'] != voices.PREVIEW_TEXT

    # 4. The preview route refuses to serve anything outside its own naming.
    for bad_name in ('..%2Fsecret.mp3', generate_body['filename'], 'preview_short.mp3'):
        blocked = client.get('/api/voice-preview/' + bad_name)
        assert blocked.status_code == 404, (
            f"preview route served {bad_name!r} with status {blocked.status_code}"
        )


def test_dalia_is_accepted_and_used_for_the_sample():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake
    client, token = new_client()

    response = post_preview(client, token, {'voice': DALIA_VOICE})
    assert response.status_code == 200, response.get_data(as_text=True)

    body = response.get_json()
    assert body['success'] is True
    assert body['voice'] == DALIA_VOICE
    assert PREVIEW_URL_RE.match(body['audio_url']), f"unexpected audio_url: {body['audio_url']}"

    assert fake.count == 1, f"expected 1 generation, got {fake.count}"
    assert fake.calls[0]['voice'] == DALIA_VOICE, (
        f"sample generated with {fake.calls[0]['voice']!r} instead of {DALIA_VOICE!r}"
    )
    assert fake.calls[0]['text'] == voices.PREVIEW_TEXT

    served = client.get(body['audio_url'])
    assert served.status_code == 200, f"serving Dalia's preview returned {served.status_code}"
    assert served.get_data() == b'ID3-FAKE-MP3-' + DALIA_VOICE.encode('utf-8')


def test_mexican_catalog_is_dalia_and_jorge():
    client, _ = new_client()
    page = client.get('/').get_data(as_text=True)

    mexican_group = next(g for g in voices.VOICE_GROUPS if g['id'] == 'es-MX')
    assert [v['id'] for v in mexican_group['voices']] == sorted(MEXICAN_CATALOG), (
        f"unexpected Mexican catalog: {[v['id'] for v in mexican_group['voices']]}"
    )

    for voice_id, expected_label in MEXICAN_CATALOG.items():
        assert voice_id in voices.ALLOWED_VOICE_IDS, f"{voice_id} not accepted by the API"
        assert voices.VOICES_BY_ID[voice_id]['label'] == expected_label, (
            f"label for {voice_id} is {voices.VOICES_BY_ID[voice_id]['label']!r}, "
            f"expected {expected_label!r}"
        )
        assert voice_id in page, f"voice {voice_id} missing from the template"
        assert expected_label in page, f"label {expected_label!r} missing from the template"


def test_catalog_is_shared_and_discarded_voices_excluded():
    fake = FakeEdgeTTS()
    app_module.generate_mp3_sync = fake

    # The catalog is the single source of truth for template and endpoints.
    client, token = new_client()
    page = client.get('/').get_data(as_text=True)
    for label in ('España', 'México', 'Latinoamérica'):
        assert f'<optgroup label="' in page and label in page, f"missing optgroup {label}"
    for voice in voices.ALL_VOICES:
        assert voice['id'] in page, f"voice {voice['id']} missing from the template"
        assert voice['label'] in page, f"friendly label for {voice['id']} missing"

    # Nothing is pending verification any more.
    assert list(voices.PENDING_VOICES) == [], f"unexpected pending voices: {voices.PENDING_VOICES}"

    # Voices discarded by the real validation are neither offered nor accepted.
    assert {v['id'] for v in voices.DISCARDED_VOICES} == set(DISCARDED_MEXICAN_VOICES)
    for voice_id in DISCARDED_MEXICAN_VOICES:
        assert voice_id not in voices.ALLOWED_VOICE_IDS
        assert voice_id not in page
        rejected = post_preview(client, token, {'voice': voice_id})
        assert rejected.status_code == 400, (
            f"{voice_id} should be rejected with 400, got {rejected.status_code}"
        )


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

TESTS = [
    test_valid_voice_generates_and_serves_preview,
    test_arbitrary_voice_is_rejected,
    test_csrf_is_required,
    test_fixed_preview_text_and_parameters,
    test_second_request_is_served_from_cache,
    test_concurrent_requests_generate_once,
    test_preview_is_separate_from_main_audio,
    test_dalia_is_accepted_and_used_for_the_sample,
    test_mexican_catalog_is_dalia_and_jorge,
    test_catalog_is_shared_and_discarded_voices_excluded,
]


def main():
    original_generate = app_module.generate_mp3_sync
    setup_module_dirs()
    failures = []
    try:
        for test in TESTS:
            reset_state()
            try:
                test()
                print(f"  ok   {test.__name__}")
            except Exception:
                failures.append(test.__name__)
                print(f"  FAIL {test.__name__}")
                traceback.print_exc()
    finally:
        app_module.generate_mp3_sync = original_generate
        teardown_module_dirs()

    if failures:
        print(f"\n{len(failures)} test(s) failed: {', '.join(failures)}")
        return 1

    print(f"\n{len(TESTS)} tests run")
    print("voice preview tests passed")
    return 0


if __name__ == '__main__':
    sys.exit(main())
