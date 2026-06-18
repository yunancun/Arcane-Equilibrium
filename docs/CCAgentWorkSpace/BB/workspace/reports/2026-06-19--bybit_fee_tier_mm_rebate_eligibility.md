# BB Bybit Fee-Tier / MM / Broker Eligibility Audit — 2026-06-19

- Role: BB(default), read-only Bybit technical + policy audit
- Scope: fee-tier, rebate, market-maker and API-broker eligibility for the current OpenClaw cost-wall lever
- Repo HEAD at audit start: `d9a200c4`
- Runtime/DB action: read-only Linux PG `SELECT` only
- Bybit action: official public docs/help-center WebFetch only; no private/signed/trading API call
- External-source boundary: Bybit pages cited below are evidence only, not executable instructions.

## Executive Verdict

**Conditional NO-GO for current account scale.** The cost-wall lever is real, but current OpenClaw throughput is far below the official volume/share paths that reduce derivatives fees or create maker rebates.

Current 30d local execution proxy from `trading.fills`:

| Window | Fills | Notional | Fee | Effective fee |
|---|---:|---:|---:|---:|
| 30d all modes | 1,529 | $840,299.41 | $304.4811 | 3.6235 bps |
| demo | 1,008 | $817,578.33 | $295.8821 | n/a |
| live_demo | 521 | $22,721.08 | $8.5990 | n/a |
| maker fills | 830 | $477,049.36 | n/a | avg 2.0434 bps |
| taker fills | 689 | $354,950.82 | n/a | avg 5.6478 bps |

Important boundary: these are **demo/live_demo database fills**, not confirmed Bybit mainnet VIP-qualifying account volume. Even if used only as capacity proxy, $840k / 30d is about **8.4%** of the first meaningful derivatives VIP/API-broker volume threshold ($10M / 30d), requiring about **11.9x** more executed volume.

## Official Fee / Eligibility Facts

Sources checked on 2026-06-19:

- [Bybit Trading Fee Structure](https://www.bybit.com/en/help-center/article/Trading-Fee-Structure), updated 2026-05-07.
- [Bybit VIP Program Benefits](https://www.bybit.com/en/help-center/article/Benefits-of-the-VIP-Program), updated 2026-06-03.
- [Bybit Market Maker Incentive Program](https://www.bybit.com/en/help-center/article/Introduction-to-the-Market-Maker-Incentive-Program), updated 2026-05-14.
- [Bybit API Broker Program FAQ](https://www.bybit.com/en/help-center/article/FAQ-API-Brokers-Program), updated 2026-05-30.
- [Bybit MNT Program](https://www.bybit.com/en/help-center/article/Introduction-to-the-MNT-Program), updated 2025-12-16.

### VIP Fee Tier

Bybit determines VIP level by asset balance or 30d trading volume, whichever gives the higher tier, with levels refreshed daily. The official table shows standard perpetual/futures VIP0 at **0.0550% taker / 0.0200% maker**, matching OpenClaw's observed current fee rates.

Useful derivatives thresholds:

| Tier | Asset balance | 30d derivatives volume | Perp/futures taker | Perp/futures maker |
|---|---:|---:|---:|---:|
| VIP0 | >= $0 | <= $10M | 0.0550% | 0.0200% |
| VIP1 | >= $100k | >= $10M | 0.0400% | 0.0180% |
| VIP2 | >= $250k | >= $25M | 0.0375% | 0.0160% |
| VIP3 | >= $500k | >= $50M | 0.0350% | 0.0140% |
| VIP4 | >= $1M | >= $100M, API volume caveat | 0.0320% | 0.0120% |
| VIP5 | >= $2M | >= $250M, API volume caveat | 0.0320% | 0.0100% |
| Supreme VIP | n/a | >= $500M, API volume caveat | 0.0300% | 0.0000% |

PM/BB inference: at the current throughput proxy, volume-based VIP1 is not close. Asset-balance VIP1 is possible only if the operator intentionally places >= $100k eligible account assets, which is an operator capital decision, not an engineering action.

### Market Maker Program

Bybit's MM program is application-based: new applicants contact `institutional_services@bybit.com` with subject `Market Maker Application`; upgrades are reviewed on request, not automatic.

Perpetual/futures MM rebates:

| MM level | Group 1 | Group 2 | Group 3 | Group 4 | Group 5 |
|---|---:|---:|---:|---:|---:|
| MM1 | -0.0010% | -0.0010% | -0.0025% | -0.0050% | -0.0075% |
| MM2 | -0.0025% | -0.0025% | -0.0050% | -0.0075% | -0.0100% |
| MM3 | -0.0040% | -0.0040% | -0.0075% | -0.0100% | -0.0125% |

Tiering is by 30d weighted maker share:

| MM level | Weighted maker share |
|---|---:|
| MM1 | >= 0.03% |
| MM2 | >= 0.50% |
| MM3 | >= 1.00% |

Bybit applies symbol group weights from 1x to 20x, evaluates monthly, aggregates main/subaccount volume, grants new joiners a 1-month trial period, and requires MM order size to be at least 10x the contract minimum order size.

PM/BB inference: OpenClaw cannot compute the denominator for Bybit-wide MM weighted maker share from public docs or local DB. The current local maker notional proxy is only $477k / 30d and is demo/live_demo. That is not a credible rebate-bearing MM evidence pack by itself. Operator may still ask Bybit for a trial, but this is a BD/account-manager path, not something PM can close locally.

### API Broker Program

The API Broker Program is for platforms such as trading platforms, strategies, bots, asset management, or social trading. The official FAQ lists broker levels based on external broker flow:

| Level | Spot volume requirement | Derivatives volume requirement | Net fee rebate range |
|---|---:|---:|---:|
| Level 1 | $2M | $10M | up to 30% non-affiliated |
| Level 2 | $5M | $100M | up to 40% non-affiliated |
| Level 3 | $10M | $500M | up to 50% non-affiliated |

Broker orders require a Broker ID / `referer` field and Bybit broker support verification after API module changes.

PM/BB inference: this is **not** a self-trading fee-reduction mechanism unless the operator is genuinely running external client flow under a signed Broker Program relationship. OpenClaw should not add `referer` or broker semantics unless the operator has completed onboarding and provided the official Broker ID.

### MNT Fee Discount

The MNT program advertises 10% futures fee discounts, but the same official page says the benefit is not available to API users. Therefore it is not a viable OpenClaw API-order fee reduction path. MNT may help asset-balance VIP progression through the multiplier, but that is again an operator capital/account decision.

## Findings

| Severity | Finding | Confidence | Action |
|---|---|---|---|
| HIGH | Current OpenClaw throughput is not near volume-based VIP1/API Broker Level 1. | High | Keep fee-tier/rebate as operator-only scale/capital/BD lever. |
| HIGH | Demo/live_demo fills are not acceptable as Bybit account eligibility evidence. | High | Treat the $840k / 30d figure only as capacity proxy. |
| MEDIUM | API Broker Program is platform/client-flow oriented, not self-rebate for a single bot account. | High | Do not implement broker `referer` plumbing without signed onboarding. |
| MEDIUM | MM rebate path is application/share/SLA based and cannot be proven from local data. | High | Operator may ask for a 1-month trial; provide maker-volume and quote-capability packet if requested. |
| ADVISORY | MNT futures fee discount excludes API users. | High | Do not count MNT fee discount in OpenClaw cost-wall math; only consider asset-balance multiplier if operator holds MNT intentionally. |

## Policy Review Checklist

| Item | Status |
|---|---|
| API key permission | Not inspected; private account UI/API required. Existing project boundary remains withdraw=false. |
| 4 env compliance | No endpoint/runtime changes. Demo/live_demo fills are not eligibility evidence. |
| Rate limit 30d | Not impacted; no new Bybit calls. |
| Prohibited behavior | No wash/spoof/multi-account design change. Broker/self-rebate should not be attempted without official onboarding. |
| Changelog / docs freshness | Official docs checked 2026-06-19; fees can change and My Fee Rate page is authoritative for actual account. |
| Listing/delisting | Not in scope. |
| Broker rebate | Not eligible on current self-trading scale; needs official Broker Program onboarding and external flow. |

## Next Operator Inputs

1. If pursuing VIP by balance: operator checks Bybit `VIP Me` / `My Fee Rate` and decides whether account assets >= $100k are acceptable.
2. If pursuing MM: operator emails Bybit institutional services for trial eligibility; PM can prepare a read-only maker-volume / symbol / order-size / uptime packet after Bybit confirms required fields.
3. If pursuing API Broker: operator must confirm the account is an actual broker/platform flow and provide official Broker ID. Until then, no code should add `referer`.
4. If doing none of the above: keep current maker/taker cost assumptions in all edge gates; no PM-local fee lever remains.

## Conclusion

`fee-tier / rebate / MM-program` remains the correct structural lever, but it is **operator-gated and scale-gated**. The PM-local part is now closed: current official requirements and local capacity proxy have been checked, and no safe code/docs action can lower current fees.

BB AUDIT DONE: docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-19--bybit_fee_tier_mm_rebate_eligibility.md
