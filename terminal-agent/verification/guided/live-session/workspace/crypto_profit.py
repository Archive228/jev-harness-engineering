#!/usr/bin/env python3
"""Интерактивный калькулятор результата одной криптосделки."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext


ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class TradeResult:
    purchase_cost: Decimal
    sale_proceeds: Decimal
    total_fees: Decimal
    profit: Decimal
    return_percent: Decimal


def validate_amount(
    value: Decimal, *, allow_zero: bool = False, fee: bool = False
) -> None:
    if not value.is_finite():
        raise ValueError("введите конечное число; NaN и бесконечность недопустимы.")
    if fee:
        if not ZERO <= value < HUNDRED:
            raise ValueError("комиссия должна быть от 0% включительно до 100% не включительно.")
    elif allow_zero:
        if value < ZERO:
            raise ValueError("значение должно быть неотрицательным (0 или больше).")
    elif value <= ZERO:
        raise ValueError("значение должно быть больше нуля.")


def calculate_trade(
    buy_price: Decimal,
    quantity: Decimal,
    sell_price: Decimal,
    buy_fee_percent: Decimal = ZERO,
    sell_fee_percent: Decimal = ZERO,
) -> TradeResult:
    validate_amount(buy_price)
    validate_amount(quantity)
    validate_amount(sell_price, allow_zero=True)
    validate_amount(buy_fee_percent, fee=True)
    validate_amount(sell_fee_percent, fee=True)

    with localcontext() as context:
        context.prec = 50
        purchase_value = buy_price * quantity
        sale_value = sell_price * quantity
        buy_fee = purchase_value * buy_fee_percent / HUNDRED
        sell_fee = sale_value * sell_fee_percent / HUNDRED
        purchase_cost = purchase_value + buy_fee
        sale_proceeds = sale_value - sell_fee
        profit = sale_proceeds - purchase_cost
        return TradeResult(
            purchase_cost=purchase_cost,
            sale_proceeds=sale_proceeds,
            total_fees=buy_fee + sell_fee,
            profit=profit,
            return_percent=profit / purchase_cost * HUNDRED,
        )


def read_amount(
    label: str, *, allow_zero: bool = False, fee: bool = False
) -> Decimal:
    prompt = f"{label}{' [Enter = 0]' if fee else ''}: "
    while True:
        raw = input(prompt).strip()
        if not raw and fee:
            return ZERO
        try:
            value = Decimal(raw.replace(",", "."))
        except InvalidOperation:
            print("Ошибка: введите число, например 100 или 0,25.")
            continue
        try:
            validate_amount(value, allow_zero=allow_zero, fee=fee)
        except ValueError as error:
            print(f"Ошибка: {error}")
            continue
        return value


def format_number(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def main() -> int:
    print("Калькулятор прибыли от криптосделки")
    print("Продажа всего купленного количества. Все цены — в одной валюте.")
    print("Дробные числа: через точку или запятую. Комиссии: в процентах.")
    try:
        buy_price = read_amount("Цена покупки за монету")
        quantity = read_amount("Количество монет")
        sell_price = read_amount("Цена продажи за монету", allow_zero=True)
        buy_fee = read_amount("Комиссия покупки, %", fee=True)
        sell_fee = read_amount("Комиссия продажи, %", fee=True)
    except (EOFError, KeyboardInterrupt):
        print("\nРасчёт отменён: ввод прерван.")
        return 1

    result = calculate_trade(buy_price, quantity, sell_price, buy_fee, sell_fee)
    print("\nРезультат (денежные суммы — в валюте введённых цен):")
    print(f"Затраты на покупку с комиссией: {format_number(result.purchase_cost)}")
    print(f"Поступления после продажи и комиссии: {format_number(result.sale_proceeds)}")
    print(f"Общая комиссия: {format_number(result.total_fees)}")
    print(f"Чистая прибыль / убыток: {format_number(result.profit)}")
    print(f"Доходность относительно затрат: {format_number(result.return_percent)}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
