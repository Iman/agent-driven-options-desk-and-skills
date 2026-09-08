Feature: Start a research desk with a supplied chain
  A researcher can inspect synthetic teaching inputs without an external provider.
  Rejected input must leave existing research artifacts intact.

  Scenario: Import a chain and compare structures
    Given a synthetic chain and an empty desk
    When I import the chain with data rights confirmed
    And I calculate Greeks, positioning, and structure comparisons
    Then the desk contains usable research results with source notes

  Scenario Outline: Refuse an incomplete import
    Given a synthetic chain and an empty desk
    When I import with <problem>
    Then the import is refused and no chain is written
    Examples:
      | problem           |
      | unconfirmed rights |
      | missing spot       |
      | missing source     |

  Scenario: A malformed replacement preserves existing research
    Given a synthetic chain and an empty desk
    And I import the chain with data rights confirmed
    When I try to replace it with malformed JSON
    Then the import is refused and the saved chain is unchanged

  Scenario: Contracts without volatility are skipped
    Given a synthetic chain and an empty desk
    And one contract has neither prices nor implied volatility
    When I import the chain with data rights confirmed
    And I calculate the full Greek ladder
    Then the unpriced contract is counted as skipped without invented volatility
