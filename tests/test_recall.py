"""Tests for the recall API — context injection for agents."""

from unittest.mock import MagicMock, patch

from clawgraph.db import GraphDB
from clawgraph.memory import Memory


def _populate_graph(db: GraphDB) -> None:
    """Pre-populate a graph with a small test dataset.

    Graph structure:
        Alice (Person) --WORKS_AT--> Acme Corp (Company)
        Alice (Person) --LEADS--> Platform Team (Team)
        Acme Corp (Company) --LOCATED_IN--> San Francisco (City)
        Bob (Person) --WORKS_AT--> Acme Corp (Company)
        Bob (Person) --MEMBER_OF--> Platform Team (Team)
        Deployment (Process) --USES--> Kubernetes (Tool)
        Platform Team (Team) --OWNS--> Deployment (Process)
    """
    entities = [
        ("Alice", "Person"),
        ("Bob", "Person"),
        ("Acme Corp", "Company"),
        ("Platform Team", "Team"),
        ("San Francisco", "City"),
        ("Deployment", "Process"),
        ("Kubernetes", "Tool"),
    ]
    for name, label in entities:
        db.execute(
            f"MERGE (e:Entity {{name: '{name}'}}) SET e.label = '{label}'"
        )

    relationships = [
        ("Alice", "Acme Corp", "WORKS_AT"),
        ("Alice", "Platform Team", "LEADS"),
        ("Acme Corp", "San Francisco", "LOCATED_IN"),
        ("Bob", "Acme Corp", "WORKS_AT"),
        ("Bob", "Platform Team", "MEMBER_OF"),
        ("Deployment", "Kubernetes", "USES"),
        ("Platform Team", "Deployment", "OWNS"),
    ]
    for from_name, to_name, rel_type in relationships:
        db.execute(
            f"MATCH (a:Entity {{name: '{from_name}'}}), "
            f"(b:Entity {{name: '{to_name}'}}) "
            f"MERGE (a)-[r:Relates {{type: '{rel_type}'}}]->(b)"
        )


def _mock_llm_response(content: str) -> MagicMock:
    """Build a mock OpenAI client that returns the given content."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


class TestRecallBasic:
    """Basic recall tests with pre-populated graph and mocked LLM."""

    @patch("clawgraph.llm._get_client")
    def test_recall_returns_relevant_facts(
        self, mock_get_client: MagicMock
    ) -> None:
        mock_get_client.return_value = _mock_llm_response(
            '["Alice", "Acme Corp"]'
        )

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        result = mem.recall("Tell me about Alice and her company")

        assert result.startswith("Known facts:\n")
        assert "Alice" in result
        assert "Acme Corp" in result

    @patch("clawgraph.llm._get_client")
    def test_recall_includes_multi_hop(
        self, mock_get_client: MagicMock
    ) -> None:
        """Recall should traverse 2 hops: Alice -> Acme -> San Francisco."""
        mock_get_client.return_value = _mock_llm_response('["Alice"]')

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        result = mem.recall("user is asking about Alice")

        assert "Alice" in result
        # 1-hop: Acme Corp and Platform Team
        assert "Acme Corp" in result
        assert "Platform Team" in result
        # 2-hop from Alice via Acme Corp: San Francisco
        assert "San Francisco" in result

    @patch("clawgraph.llm._get_client")
    def test_recall_deployment_context(
        self, mock_get_client: MagicMock
    ) -> None:
        """Recall about deployment should return Kubernetes and related team."""
        mock_get_client.return_value = _mock_llm_response(
            '["Deployment", "Kubernetes"]'
        )

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        result = mem.recall("user is asking about deployment")

        assert "Deployment" in result
        assert "Kubernetes" in result
        # Platform Team owns Deployment (1-hop from Deployment)
        assert "Platform Team" in result

    @patch("clawgraph.llm._get_client")
    def test_recall_natural_language_format(
        self, mock_get_client: MagicMock
    ) -> None:
        """Output should be human-readable, not JSON."""
        mock_get_client.return_value = _mock_llm_response('["Alice"]')

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        result = mem.recall("about Alice")

        # Should be natural language, not JSON
        assert "{" not in result
        assert "}" not in result
        # Each fact should be a bullet point
        lines = result.strip().split("\n")
        assert lines[0] == "Known facts:"
        for line in lines[1:]:
            assert line.startswith("- ")


class TestRecallEmptyAndEdge:
    """Edge cases for recall()."""

    def test_recall_empty_graph(self) -> None:
        """Recall on empty graph should return empty string."""
        mem = Memory(db_path=":memory:")
        result = mem.recall("anything")
        assert result == ""

    @patch("clawgraph.llm._get_client")
    def test_recall_no_relevant_entities(
        self, mock_get_client: MagicMock
    ) -> None:
        """LLM finds nothing relevant — return empty string."""
        mock_get_client.return_value = _mock_llm_response("[]")

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        result = mem.recall("something completely unrelated to the graph")
        assert result == ""

    def test_recall_empty_context(self) -> None:
        """Empty context string should return empty string."""
        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        assert mem.recall("") == ""
        assert mem.recall("   ") == ""

    @patch("clawgraph.llm._get_client")
    def test_recall_llm_returns_invalid_json(
        self, mock_get_client: MagicMock
    ) -> None:
        """If LLM returns garbage, recall should return empty string gracefully."""
        mock_get_client.return_value = _mock_llm_response("not json at all")

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        # Should not raise — graceful degradation
        result = mem.recall("about Alice")
        assert result == ""

    @patch("clawgraph.llm._get_client")
    def test_recall_llm_returns_nonexistent_entities(
        self, mock_get_client: MagicMock
    ) -> None:
        """If LLM returns entity names not in the graph, they are filtered out."""
        mock_get_client.return_value = _mock_llm_response(
            '["NonExistent", "AlsoFake"]'
        )

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        result = mem.recall("about something fake")
        assert result == ""


class TestRecallTokenBudget:
    """Tests for max_tokens budget trimming."""

    @patch("clawgraph.llm._get_client")
    def test_recall_respects_max_tokens(
        self, mock_get_client: MagicMock
    ) -> None:
        """Output should respect the token budget (4 chars ≈ 1 token)."""
        mock_get_client.return_value = _mock_llm_response(
            '["Alice", "Acme Corp", "Deployment", "Kubernetes"]'
        )

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        # Very small budget — should truncate
        result = mem.recall("everything", max_tokens=50)

        # 50 tokens * 4 chars = 200 chars max
        assert len(result) <= 200

    @patch("clawgraph.llm._get_client")
    def test_recall_large_budget_returns_all(
        self, mock_get_client: MagicMock
    ) -> None:
        """Large budget should return all relevant facts."""
        mock_get_client.return_value = _mock_llm_response(
            '["Alice", "Deployment"]'
        )

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        result = mem.recall("tell me everything", max_tokens=10000)

        assert "Alice" in result
        assert "Deployment" in result
        assert "Kubernetes" in result

    @patch("clawgraph.llm._get_client")
    def test_recall_truncates_least_relevant(
        self, mock_get_client: MagicMock
    ) -> None:
        """When truncating, facts about more-relevant entities come first."""
        # Alice is first (most relevant), Deployment second
        mock_get_client.return_value = _mock_llm_response(
            '["Alice", "Deployment"]'
        )

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        # Use a small enough budget that not all facts fit
        result_small = mem.recall("about Alice and deployment", max_tokens=40)
        # Alice facts should appear before Deployment facts
        if "Alice" in result_small and "Deployment" in result_small:
            assert result_small.index("Alice") < result_small.index("Deployment")


class TestRecallLLMInteraction:
    """Tests for how recall interacts with the LLM."""

    @patch("clawgraph.llm._get_client")
    def test_recall_passes_entity_names_to_llm(
        self, mock_get_client: MagicMock
    ) -> None:
        """LLM should receive the list of all entity names."""
        mock_client = _mock_llm_response('["Alice"]')
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        mem.recall("about Alice")

        # Check the LLM was called with entity names in the prompt
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_msg = messages[1]["content"]
        assert "Alice" in user_msg
        assert "Acme Corp" in user_msg
        assert "Kubernetes" in user_msg

    @patch("clawgraph.llm._get_client")
    def test_recall_only_one_llm_call(
        self, mock_get_client: MagicMock
    ) -> None:
        """Recall should make exactly one LLM call (for relevance scoring)."""
        mock_client = _mock_llm_response('["Alice"]')
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        mem.recall("about Alice")

        assert mock_client.chat.completions.create.call_count == 1

    @patch("clawgraph.llm._get_client")
    def test_recall_handles_llm_api_error(
        self, mock_get_client: MagicMock
    ) -> None:
        """If the LLM API fails entirely, recall returns empty string."""
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )
        mock_get_client.return_value = mock_client

        mem = Memory(db_path=":memory:")
        _populate_graph(mem._db)

        # Should not raise
        result = mem.recall("about Alice")
        assert result == ""


class TestGetNeighborhood:
    """Tests for GraphDB.get_neighborhood()."""

    def test_neighborhood_single_hop(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _populate_graph(db)

        result = db.get_neighborhood("Alice", hops=1)
        assert result["entity"] is not None
        assert result["entity"]["e.name"] == "Alice"

        neighbor_names = {e["e.name"] for e in result["entities"]}
        # Direct connections: Acme Corp, Platform Team
        assert "Acme Corp" in neighbor_names
        assert "Platform Team" in neighbor_names
        # 2-hop away: should NOT appear
        assert "San Francisco" not in neighbor_names

    def test_neighborhood_two_hops(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _populate_graph(db)

        result = db.get_neighborhood("Alice", hops=2)
        neighbor_names = {e["e.name"] for e in result["entities"]}
        # 2-hop: San Francisco (via Acme Corp)
        assert "San Francisco" in neighbor_names
        # Also Bob (via Acme Corp or Platform Team)
        assert "Bob" in neighbor_names

    def test_neighborhood_nonexistent_entity(self) -> None:
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _populate_graph(db)

        result = db.get_neighborhood("NonExistent", hops=2)
        assert result["entity"] is None
        assert result["entities"] == []
        assert result["relationships"] == []

    def test_neighborhood_no_schema(self) -> None:
        """If tables don't exist, return empty result."""
        db = GraphDB(db_path=":memory:")
        # Don't call ensure_base_schema()
        result = db.get_neighborhood("Anything")
        assert result["entity"] is None

    def test_neighborhood_isolated_entity(self) -> None:
        """Entity with no relationships returns empty neighbors."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        db.execute("MERGE (e:Entity {name: 'Isolated'}) SET e.label = 'Thing'")

        result = db.get_neighborhood("Isolated")
        assert result["entity"] is not None
        assert result["entity"]["e.name"] == "Isolated"
        assert result["entities"] == []
        assert result["relationships"] == []

    def test_neighborhood_incoming_relationships(self) -> None:
        """Should find entities connected via incoming edges."""
        db = GraphDB(db_path=":memory:")
        db.ensure_base_schema()
        _populate_graph(db)

        # Acme Corp has incoming edges from Alice and Bob
        result = db.get_neighborhood("Acme Corp", hops=1)
        neighbor_names = {e["e.name"] for e in result["entities"]}
        assert "Alice" in neighbor_names
        assert "Bob" in neighbor_names
        # Also outgoing to San Francisco
        assert "San Francisco" in neighbor_names


class TestIdentifyRelevantEntities:
    """Tests for the LLM relevance scoring function."""

    @patch("clawgraph.llm._get_client")
    def test_returns_relevant_names(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import identify_relevant_entities

        mock_get_client.return_value = _mock_llm_response(
            '["Alice", "Acme Corp"]'
        )

        result = identify_relevant_entities(
            "about Alice", ["Alice", "Bob", "Acme Corp"]
        )
        assert result == ["Alice", "Acme Corp"]

    @patch("clawgraph.llm._get_client")
    def test_filters_nonexistent_names(
        self, mock_get_client: MagicMock
    ) -> None:
        from clawgraph.llm import identify_relevant_entities

        mock_get_client.return_value = _mock_llm_response(
            '["Alice", "NotInGraph"]'
        )

        result = identify_relevant_entities(
            "about Alice", ["Alice", "Bob"]
        )
        assert result == ["Alice"]

    def test_empty_entity_list(self) -> None:
        from clawgraph.llm import identify_relevant_entities

        result = identify_relevant_entities("anything", [])
        assert result == []

    @patch("clawgraph.llm._get_client")
    def test_invalid_json_returns_empty(
        self, mock_get_client: MagicMock
    ) -> None:
        from clawgraph.llm import identify_relevant_entities

        mock_get_client.return_value = _mock_llm_response("not valid json")

        result = identify_relevant_entities(
            "about Alice", ["Alice"]
        )
        assert result == []

    @patch("clawgraph.llm._get_client")
    def test_strips_code_fences(self, mock_get_client: MagicMock) -> None:
        from clawgraph.llm import identify_relevant_entities

        mock_get_client.return_value = _mock_llm_response(
            '```json\n["Alice"]\n```'
        )

        result = identify_relevant_entities(
            "about Alice", ["Alice", "Bob"]
        )
        assert result == ["Alice"]

    @patch("clawgraph.llm._get_client")
    def test_api_error_returns_empty(
        self, mock_get_client: MagicMock
    ) -> None:
        from openai import APIConnectionError

        from clawgraph.llm import identify_relevant_entities

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )
        mock_get_client.return_value = mock_client

        result = identify_relevant_entities(
            "about Alice", ["Alice"]
        )
        assert result == []


class TestSerializeFacts:
    """Tests for the _serialize_facts helper."""

    def test_formats_relationships(self) -> None:
        from clawgraph.memory import _serialize_facts

        facts = [
            ("Alice", "Person", "WORKS_AT", "Acme", "Company"),
        ]
        lines = _serialize_facts(facts, ["Alice"])
        assert len(lines) == 1
        assert "Alice (Person)" in lines[0]
        assert "works at" in lines[0]
        assert "Acme (Company)" in lines[0]

    def test_relevance_ordering(self) -> None:
        from clawgraph.memory import _serialize_facts

        facts = [
            ("Bob", "Person", "WORKS_AT", "Acme", "Company"),
            ("Alice", "Person", "WORKS_AT", "Acme", "Company"),
        ]
        # Alice is more relevant than Bob
        lines = _serialize_facts(facts, ["Alice", "Bob"])
        assert "Alice" in lines[0]
        assert "Bob" in lines[1]

    def test_empty_labels(self) -> None:
        from clawgraph.memory import _serialize_facts

        facts = [("X", "", "KNOWS", "Y", "")]
        lines = _serialize_facts(facts, ["X"])
        assert lines[0] == "- X knows Y"

    def test_empty_facts(self) -> None:
        from clawgraph.memory import _serialize_facts

        lines = _serialize_facts([], ["Alice"])
        assert lines == []
