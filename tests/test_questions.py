from contract_stack.models import Attribute
from contract_stack.questions import interpret_question


def test_supported_limit_question() -> None:
    result = interpret_question("What is the current On Premises single loss limit?")
    assert result.attribute == Attribute.LIMIT
    assert result.subject == "On Premises"


def test_unsupported_question_is_not_forced_into_ontology() -> None:
    result = interpret_question("What is the current territorial coverage?")
    assert result.attribute == Attribute.UNSUPPORTED
    assert result.subject is None
