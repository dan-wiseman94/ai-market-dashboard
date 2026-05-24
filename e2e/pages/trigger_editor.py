"""Trigger editor page — /triggers/new or /triggers/:id."""

from __future__ import annotations

import json

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class TriggerEditorPage(BasePage):
    def go_new(self) -> None:
        self.goto("/triggers/new")

    def go(self, trigger_id: int) -> None:
        self.goto(f"/triggers/{trigger_id}")

    @property
    def name(self) -> Locator:
        return self.page.get_by_label("Name")

    @property
    def ticker(self) -> Locator:
        return self.page.get_by_label("Ticker")

    @property
    def metric(self) -> Locator:
        return self.page.get_by_label("Metric")

    @property
    def op(self) -> Locator:
        return self.page.get_by_label("Op")

    @property
    def value(self) -> Locator:
        return self.page.get_by_label("Value")

    @property
    def dsl_json(self) -> Locator:
        return self.page.get_by_label("DSL JSON")

    @property
    def backtest_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Backtest")

    @property
    def fire_now_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Fire now")

    def fill_simple(self, *, name: str, ticker: str, metric: str, op: str, value: str) -> None:
        self.name.fill(name)
        self.ticker.fill(ticker)
        self.metric.select_option(value=metric)
        self.op.select_option(value=op)
        self.value.fill(value)

    def fill_dsl(self, condition: dict) -> None:
        self.dsl_json.fill(json.dumps(condition))

    def backtest(self, start: str, end: str) -> None:
        self.page.get_by_label("Start").fill(start)
        self.page.get_by_label("End").fill(end)
        self.backtest_btn.click()

    def save(self) -> None:
        self.page.get_by_role("button", name="Save").click()
