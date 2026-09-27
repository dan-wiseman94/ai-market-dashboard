import pytest

from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread


@pytest.mark.django_db
def test_message_streaming_states():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    m = Message.objects.create(thread=t, role="user", content={"text": "hi"})
    assert m.status == "done"
    a = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="streaming")
    assert a.status == "streaming"
