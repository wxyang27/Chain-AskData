from app.semantic.contract import SemanticContractBuilder


def test_contract_maps_unverified_synonym_to_inventory_metric():
    contract = SemanticContractBuilder().build("各机构还有多少没核销的金额，排个前十")

    assert contract.intent == "nl2sql"
    assert contract.template_id == "unverified_amount_store_top10"
    assert "unverified_amount" in contract.metrics
    assert "left_num > 0" in contract.filters
    assert "sy_hospital_name" in contract.dimensions


def test_contract_maps_payment_synonym_to_payment_domain():
    contract = SemanticContractBuilder().build("近30天新客付了多少、多少人付的、人均多少")

    assert contract.template_id == "new_customer_payment_30d"
    assert contract.domain == "payment"
    assert {"payment_gmv", "payment_user_count", "payment_aov_by_user_day"}.issubset(
        set(contract.metrics)
    )
    assert "is_paydate_cash = 0" in contract.filters
    assert "is_pay_new = 1" in contract.filters


def test_contract_rejects_prediction_and_diagnostic_questions():
    builder = SemanticContractBuilder()

    assert builder.build("帮我预测下个月收入是多少？").intent == "unknown"
    assert builder.build("为什么昨天收入下降？").intent == "unknown"
    assert builder.build("帮我分析哪个门店有问题").intent == "unknown"


def test_contract_routes_store_field_question_to_schema_explain():
    contract = SemanticContractBuilder().build("门店名称用哪个字段？")

    assert contract.intent == "schema_explain"
    assert "sy_hospital_name" in contract.required_fields


def test_contract_routes_penetration_how_to_question_to_caliber_explain():
    contract = SemanticContractBuilder().build("怎么看一个品项的大单品品项渗透率？")

    assert contract.intent == "caliber_explain"
    assert "standard_item_penetration" in contract.metrics
    assert "standard_name" in contract.required_fields


def test_contract_maps_revenue_category_dimension_and_filters():
    builder = SemanticContractBuilder()

    category_contract = builder.build("最近30天全连锁各品类的核销收入占比")
    assert "revenue_category" in category_contract.dimensions
    assert category_contract.time_range == "last_30d"

    master_contract = builder.build("最近7天大师团核销收入和新客核销人次占比")
    assert "revenue_category = '大师团'" in master_contract.filters
    assert "execution_visit_count" in master_contract.metrics
    assert master_contract.time_range == "last_7d"


def test_contract_routes_membership_question_to_schema_explain():
    contract = SemanticContractBuilder().build("怎么知道一个用户是不是连锁的L3以上会员")

    assert contract.intent == "schema_explain"
    assert "membership_level" in contract.required_fields
