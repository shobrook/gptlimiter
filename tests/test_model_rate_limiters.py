import threading
import time
import pytest
from openlimit.model_rate_limiters import ModelRateLimiter, ModelRateLimit
from openlimit.buckets import ModelBucket
from unittest.mock import patch


MODEL_GPT_3_5 = "gpt-3.5-turbo"
MODEL_GPT_4_TURBO = "gpt-4-turbo"
MODEL_GPT_4o = "gpt-4o"

def test_get_rate_limit_valid_model():
    model_rate_limits = {
        MODEL_GPT_3_5: ModelRateLimit(request_limit=10, token_limit=1000),
        MODEL_GPT_4_TURBO: ModelRateLimit(request_limit=5, token_limit=500),
    }
    rate_limiter = ModelRateLimiter(model_rate_limits=model_rate_limits, token_counter=lambda **kwargs: 100)

    assert rate_limiter.get_rate_limit(MODEL_GPT_3_5) == ModelRateLimit(request_limit=10, token_limit=1000)
    assert rate_limiter.get_rate_limit(MODEL_GPT_4_TURBO) == ModelRateLimit(request_limit=5, token_limit=500)

def test_get_rate_limit_invalid_model():
    model_rate_limits = {
        MODEL_GPT_3_5: ModelRateLimit(request_limit=10, token_limit=1000),
        MODEL_GPT_4_TURBO: ModelRateLimit(request_limit=5, token_limit=500),
    }
    rate_limiter = ModelRateLimiter(model_rate_limits=model_rate_limits, token_counter=lambda **kwargs: 100)

    with pytest.raises(ValueError):
        rate_limiter.get_rate_limit("invalid_model")

# And here is the unit test which is getting stuck
def test_limit_with_valid_model():
    model_rate_limits = {
        MODEL_GPT_3_5: ModelRateLimit(request_limit=100, token_limit=1000),
    }
    rate_limiter = ModelRateLimiter(model_rate_limits=model_rate_limits, bucket_size_in_seconds=600, token_counter=lambda **kwargs: 50)

    print("Starting test...")
    with rate_limiter.limit(model=MODEL_GPT_3_5):
        print("Inside rate limiter")
    print("Test completed")

def test_limit_with_missing_model():
    model_rate_limits = {
        MODEL_GPT_3_5: ModelRateLimit(request_limit=10, token_limit=1000),
    }
    rate_limiter = ModelRateLimiter(model_rate_limits=model_rate_limits, token_counter=lambda **kwargs: 100)

    with pytest.raises(ValueError):
        with rate_limiter.limit():
            pass

def test_model_bucket_initial_capacity():
    rate_limit_per_minute = 1200
    bucket_size_in_seconds = 600
    bucket = ModelBucket(rate_limit=rate_limit_per_minute, bucket_size_in_seconds=bucket_size_in_seconds)
    assert bucket.get_capacity() == rate_limit_per_minute / 60 * bucket_size_in_seconds

def test_model_bucket_set_capacity():
    simulated_timestamp = 123
    bucket = ModelBucket(rate_limit=120, bucket_size_in_seconds=60, last_checked=simulated_timestamp)
    bucket.set_capacity(5, current_time=simulated_timestamp)
    assert bucket.get_capacity(simulated_timestamp) == 5

def test_capacity_after_one_second():
    rate_limit_per_minute = 120
    bucket_size_in_seconds = 60
    bucket = ModelBucket(rate_limit=rate_limit_per_minute, bucket_size_in_seconds=bucket_size_in_seconds)
    bucket.set_capacity(0)
    with patch('time.time', return_value=bucket.last_checked + 1):
        assert bucket.get_capacity() == pytest.approx(rate_limit_per_minute / 60, 0.1)

def test_capacity_replenished_after_bucket_size_in_seconds():
    rate_limit_per_minute = 120
    bucket_size_in_seconds = 60
    bucket = ModelBucket(rate_limit=rate_limit_per_minute, bucket_size_in_seconds=bucket_size_in_seconds)
    bucket.set_capacity(0)
    with patch('time.time', return_value=bucket.last_checked + bucket_size_in_seconds):
        assert bucket.get_capacity() == pytest.approx(rate_limit_per_minute, 0.1)

def test_multithreading_rate_limiter():
    model_rate_limits = {
        MODEL_GPT_3_5: ModelRateLimit(request_limit=10, token_limit=1000),
    }
    rate_limiter = ModelRateLimiter(model_rate_limits=model_rate_limits, sleep_interval=0.2, token_counter=lambda **kwargs: 1000)

    def exhaust_tokens():
        with rate_limiter.limit(model=MODEL_GPT_3_5):
            print("Tokens exhausted")

    def wait_for_tokens():
        # Mock time.time to simulate time passing for wait_for_capacity_sync
        current_time = time.time()
        side_effect = [
            current_time,  # initial call in exhaust_tokens
            current_time,  # second call in exhaust_tokens
            current_time + 1,  # first sleep in wait_for_capacity_sync
            current_time + 61,  # second call after sleep, tokens replenished
        ]

        with patch('time.time', side_effect=side_effect):
            with rate_limiter.limit(model=MODEL_GPT_3_5):
                print("Tokens available")

    thread1 = threading.Thread(target=exhaust_tokens)
    thread2 = threading.Thread(target=wait_for_tokens)

    thread1.start()
    time.sleep(0.1)  # Ensure thread1 starts and exhausts tokens first
    thread2.start()