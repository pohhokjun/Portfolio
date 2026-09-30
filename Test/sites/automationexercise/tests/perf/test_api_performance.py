# -*- coding: utf-8 -*-
"""
接口性能测试（轻量版）

★ 为什么不用 JMeter ★
    JMeter 需单独安装且依赖 Java，本项目坚持「零额外安装」。
    更重要的是：用 Python 手写压测，你能讲清楚 JMeter 底层在做什么，
    这比会点几个按钮更能体现深度。

面试话术：
    「我用 concurrent.futures 做并发压测，采集 P50/P90/P95、TPS 和错误率。
      JMeter 本质也是这些事：线程组控制并发、聚合报告统计分位数、
      断言器判断成功率。我理解这套指标体系，用 JMeter 上手很快。」

性能指标（面试常问）：
    响应时间 RT   单个请求耗时
    P95          95% 的请求快于这个值 —— 比平均值更能反映真实体验
                 为什么不用平均值：100个请求99个10ms、1个10秒，
                 平均值 110ms 看着很好，但那个用户已经走了
    吞吐量 TPS    每秒完成的事务数
    错误率        失败请求占比，生产系统通常要求 < 0.1%
    并发数        同时发起请求的用户数

★ 本项目实测发现（真实的测试结论，面试可讲）★
    被测站点在 10 并发下会返回 HTTP 403，属于服务端主动限流保护。
    这不是系统缺陷，而是防护机制生效。
    所以本用例把「限流拦截」和「真实失败」分开统计 ——
    真实工作中也是如此：压测前要和运维确认是否放开限流白名单，
    否则压的是防火墙，不是应用本身。
"""

import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import allure
import pytest

from sites.automationexercise.api.product_api import ProductApi
from common.assertions import assert_true, SoftAssert
from common.logger import get_logger

log = get_logger("perf")

RATE_LIMIT_CODES = (403, 429, 503)


def percentile(data, p):
    """计算分位数。p=95 表示 P95。"""
    if not data:
        return 0
    ordered = sorted(data)
    idx = int(len(ordered) * p / 100)
    return ordered[min(idx, len(ordered) - 1)]


@allure.epic("性能测试")
@allure.feature("接口性能")
class TestApiPerformance:

    @allure.story("响应时间基线")
    @allure.title("PERF_001 - 商品列表接口单次响应时间应小于3秒")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.perf
    @pytest.mark.p2
    def test_single_request_response_time(self, cfg):
        api = ProductApi(cfg)
        resp = api.get_all_products()

        allure.attach("响应时间: %d ms" % resp.elapsed_ms,
                      name="单次响应时间",
                      attachment_type=allure.attachment_type.TEXT)

        assert_true(resp.elapsed_ms < 3000,
                    "响应时间 %dms 超过 3000ms 阈值" % resp.elapsed_ms)

    @allure.story("并发压测")
    @allure.title("PERF_002 - 商品列表接口并发压测")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "并发模型：ThreadPoolExecutor 模拟多用户同时请求\n"
        "采集指标：P50/P90/P95/最大值/平均值/TPS/错误率/限流率\n"
        "注意：这是公开测试站点，并发数刻意设得很低，避免造成压力"
    )
    @pytest.mark.perf
    @pytest.mark.p2
    def test_concurrent_load(self, cfg):
        CONCURRENCY = 5         # 并发数：对公开站点保持克制
        ROUNDS = 3
        TOTAL = CONCURRENCY * ROUNDS

        # min_interval=0 关掉主动限速，否则压不出真实并发
        api = ProductApi(cfg, min_interval=0)
        api.MAX_RETRY = 1       # 压测阶段不重试，要看真实结果

        durations, rate_limited, errors = [], [], []

        def one_request(idx):
            t0 = time.time()
            try:
                resp = api.get_all_products()
                cost = round((time.time() - t0) * 1000)
                return {"idx": idx, "ms": cost, "code": resp.status_code}
            except Exception as exc:
                return {"idx": idx, "ms": round((time.time() - t0) * 1000),
                        "code": type(exc).__name__}

        start = time.time()
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = [pool.submit(one_request, i) for i in range(TOTAL)]
            results = [f.result() for f in as_completed(futures)]
        wall = time.time() - start

        for r in results:
            if r["code"] == 200:
                durations.append(r["ms"])
            elif r["code"] in RATE_LIMIT_CODES:
                rate_limited.append(r)
            else:
                errors.append(r)

        success = len(durations)
        metrics = {
            "总请求数": TOTAL,
            "并发数": CONCURRENCY,
            "总耗时(s)": round(wall, 2),
            "TPS": round(TOTAL / wall, 2) if wall > 0 else 0,
            "成功数": success,
            "被限流数": len(rate_limited),
            "真实失败数": len(errors),
            "成功率(%)": round(success / TOTAL * 100, 2),
            "限流率(%)": round(len(rate_limited) / TOTAL * 100, 2),
            "错误率(%)": round(len(errors) / TOTAL * 100, 2),
            "平均RT(ms)": round(statistics.mean(durations)) if durations else 0,
            "最小RT(ms)": min(durations) if durations else 0,
            "最大RT(ms)": max(durations) if durations else 0,
            "P50(ms)": percentile(durations, 50),
            "P90(ms)": percentile(durations, 90),
            "P95(ms)": percentile(durations, 95),
        }

        report = "\n".join("%-14s %s" % (k, v) for k, v in metrics.items())
        log.info("性能测试结果:\n%s", report)
        allure.attach(report, name="性能指标汇总",
                      attachment_type=allure.attachment_type.TEXT)

        conclusion = []
        if rate_limited:
            conclusion.append(
                "检出服务端限流：%d/%d 请求被拒（HTTP %s）。\n"
                "结论：这是防护机制生效，非应用缺陷。\n"
                "真实项目中压测前需与运维确认放开限流白名单，"
                "否则测的是防火墙而非应用性能。"
                % (len(rate_limited), TOTAL,
                   sorted({r["code"] for r in rate_limited})))
        if errors:
            conclusion.append(
                "真实失败 %d 条：%s"
                % (len(errors), sorted({str(r["code"]) for r in errors})))
        if conclusion:
            allure.attach("\n\n".join(conclusion), name="测试结论",
                          attachment_type=allure.attachment_type.TEXT)

        # ---- 断言：性能基线 ----
        sa = SoftAssert()
        sa.true(success > 0, "至少要有成功请求才能评估性能")
        sa.less_than(metrics["错误率(%)"], 10.0, "真实错误率应低于10%")
        if durations:
            sa.less_than(metrics["P95(ms)"], 8000, "成功请求的P95应低于8秒")
        sa.assert_all()

    @allure.story("稳定性")
    @allure.title("PERF_003 - 接口连续调用稳定性（20次）")
    @allure.severity(allure.severity_level.MINOR)
    @allure.description(
        "稳定性测试：连续调用观察响应时间是否劣化。\n"
        "真实场景用于发现内存泄漏、连接池耗尽、缓存失效等问题。"
    )
    @pytest.mark.perf
    @pytest.mark.p2
    def test_stability(self, cfg):
        api = ProductApi(cfg)
        durations = []

        for _ in range(20):
            resp = api.get_all_products()
            if resp.status_code == 200:
                durations.append(resp.elapsed_ms)

        assert_true(len(durations) >= 10, "有效样本不足，无法评估稳定性")

        half = len(durations) // 2
        first_half = statistics.mean(durations[:half])
        second_half = statistics.mean(durations[half:])
        degradation = (second_half - first_half) / first_half * 100 \
            if first_half else 0

        allure.attach(
            "有效样本: %d\n前半段平均: %.0f ms\n后半段平均: %.0f ms\n"
            "劣化幅度: %.1f%%\n\n明细: %s"
            % (len(durations), first_half, second_half, degradation, durations),
            name="稳定性分析",
            attachment_type=allure.attachment_type.TEXT)

        assert_true(degradation < 150,
                    "后半段响应时间劣化 %.1f%%，可能存在性能衰减" % degradation)
