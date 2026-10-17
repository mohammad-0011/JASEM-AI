from jasem.state_machine import State, StateMachine


def test_initial_state_is_idle():
    sm = StateMachine()
    assert sm.state == State.IDLE


def test_wake_to_listening_to_processing():
    sm = StateMachine()
    assert sm.transition(State.WAKE_MONITORING)
    assert sm.transition(State.LISTENING)
    assert sm.transition(State.PROCESSING)
    assert sm.transition(State.GENERATING)
    assert sm.transition(State.SPEAKING)


def test_blocked_transition_rejected():
    sm = StateMachine()
    assert not sm.transition(State.SPEAKING)   # IDLE -> SPEAKING is illegal
    assert sm.state == State.IDLE


def test_interrupt_from_speaking():
    sm = StateMachine()
    for s in (State.WAKE_MONITORING, State.LISTENING, State.PROCESSING,
              State.GENERATING, State.SPEAKING):
        sm.transition(s)
    assert sm.transition(State.INTERRUPTED, "barge-in")
    assert sm.transition(State.WAKE_MONITORING)


def test_shutdown_is_terminal():
    sm = StateMachine()
    assert sm.transition(State.SHUTDOWN)
    assert not sm.transition(State.IDLE)


def test_listener_notified():
    seen = []
    sm = StateMachine(on_transition=lambda tr: seen.append((tr.old, tr.new)))
    sm.transition(State.WAKE_MONITORING)
    sm.transition(State.ERROR, "boom")
    assert seen == [(State.IDLE, State.WAKE_MONITORING), (State.WAKE_MONITORING, State.ERROR)]


def test_same_state_transition_is_noop_true():
    sm = StateMachine()
    assert sm.transition(State.IDLE) is True
