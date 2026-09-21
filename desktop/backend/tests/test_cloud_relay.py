from cloud.relay import InMemoryRelayBroker


def test_in_memory_relay_replaces_and_unregisters_peer():
    broker = InMemoryRelayBroker()
    first, second = object(), object()
    assert broker.register("s1", "d1", first) is None
    assert broker.peer("s1", "d1") is first
    assert broker.register("s1", "d1", second) is first
    broker.unregister("s1", "d1", first)
    assert broker.peer("s1", "d1") is second
    broker.unregister("s1", "d1", second)
    assert broker.empty("s1")
