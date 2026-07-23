from app.cot_planning.semantic_contract import SemanticContractBuilder


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


def test_contract_extracts_named_city_and_item_as_hard_filters():
    contract = SemanticContractBuilder().build("最近30天杭州奇迹胶原核销收入 TOP5门店")

    assert "city_name LIKE '%杭州%'" in contract.filters
    assert "standard_name REGEXP '奇迹胶原'" in contract.filters
    assert "city_name" in contract.required_fields
    assert "standard_name" in contract.required_fields


def test_contract_keeps_new_old_template_before_single_channel_filter():
    contract = SemanticContractBuilder().build(
        "最近30天新客和老客核销收入、人次、客单价分别是多少？，私域"
    )

    assert contract.template_id == "new_old_customer_execution_30d"
    assert "is_new" in contract.dimensions
    assert "cx_first_channel = '私域'" in contract.filters


def test_contract_routes_p1_delta_resolved_questions_to_specific_templates():
    builder = SemanticContractBuilder()

    assert (
        builder.build("最近30天整体核销收入是多少？").template_id
        == "execution_income_summary_30d"
    )
    assert (
        builder.build("最近30天品项核销收入占比 TOP20").template_id
        == "standard_item_income_share_top20_30d"
    )
    assert (
        builder.build("最近30天北京奇迹胶原支付GMV TOP5门店").template_id
        == "payment_gmv_store_topn_30d"
    )


def test_contract_maps_oral_payment_income_to_overall_payment_summary():
    builder = SemanticContractBuilder()

    contract = builder.build("本周整体支付收入是多少？")

    assert contract.template_id == "payment_gmv_summary_30d"
    assert contract.domain == "payment"
    assert contract.time_range == "this_week"
    assert contract.metrics == ["payment_gmv"]
    assert "is_paydate_cash = 0" in contract.filters
    assert "is_pay_new = 1" not in contract.filters


def test_contract_extracts_named_store_filter_without_store_grouping():
    contract = SemanticContractBuilder().build("本周整体支付GMV是多少？，北京保利店")

    assert contract.template_id == "payment_gmv_summary_30d"
    assert "sy_hospital_name LIKE '%保利%'" in contract.filters
    assert "city_name LIKE '%北京%'" in contract.filters
    assert "sy_hospital_name" in contract.required_fields
    assert "sy_hospital_name" not in contract.dimensions


def test_contract_maps_named_area_to_area_filter():
    contract = SemanticContractBuilder().build("本周华北大区支付GMV是多少？")

    assert contract.template_id == "payment_gmv_summary_30d"
    assert contract.domain == "payment"
    assert "area_name LIKE '%华北%'" in contract.filters
    assert "area_name" in contract.required_fields
    assert "area_name" not in contract.dimensions


def test_contract_maps_area_breakdown_to_area_dimension():
    execution_contract = SemanticContractBuilder().build("最近30天各大区核销收入")
    payment_contract = SemanticContractBuilder().build("最近30天各大区支付GMV")

    assert execution_contract.template_id == "area_execution_30d"
    assert "area_name" in execution_contract.dimensions
    assert "area_name" in execution_contract.required_fields
    assert "area_name LIKE" not in " ".join(execution_contract.filters)

    assert payment_contract.template_id == "area_payment_30d"
    assert payment_contract.domain == "payment"
    assert "area_name" in payment_contract.dimensions


def test_contract_routes_membership_question_to_schema_explain():
    contract = SemanticContractBuilder().build("怎么知道一个用户是不是连锁的L3以上会员")

    assert contract.intent == "schema_explain"
    assert "membership_level" in contract.required_fields
