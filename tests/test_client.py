import pytest
from tennisrungs_mcp.client import Client
from tennisrungs_mcp.models import IntegrationError
from fixtures import dashboard, HISTORY, RANKINGS


class Fake:
    def __init__(self): self.calls = []
    def get(self, path, *, private=False):
        self.calls.append((path, private))
        return HISTORY if path.startswith('/Public/') else RANKINGS if path.startswith('/Ladders/') else dashboard()


def test_supported_reads_use_expected_scope_and_coverage():
    fake = Fake()
    client = Client(fake)
    assert client.list_current_ladders().complete
    assert client.list_own_matches().rows[0].opponent == 'Demo Opponent'
    assert client.list_own_proposals().rows[0].status == 'PROPOSED'
    assert client.list_open_proposals().rows[0].proposer == 'Demo Player'
    assert client.get_rankings(101).rows[0].team_id == 201
    assert client.get_player_history(201).rows[0].result == 'L'
    assert all(private for _, private in fake.calls[:-1])
    assert fake.calls[-1] == ('/Public/PlayerMatches?teamId=201', False)


@pytest.mark.parametrize('value', [True, 0, -1, '101', None])
def test_invalid_ids_do_not_trigger_network(value):
    fake = Fake()
    with pytest.raises(IntegrationError): Client(fake).get_rankings(value)
    with pytest.raises(IntegrationError): Client(fake).get_player_history(value)
    assert fake.calls == []
