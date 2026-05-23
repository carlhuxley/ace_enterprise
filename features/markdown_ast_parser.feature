Feature: Incremental Markdown AST Parser

  Scenario: Parse absolute baseline empty state
    Given a raw markdown string ""
    When the AST parser executes
    Then the returned structure must be {"type": "root", "children": []}

  Scenario: Parse a single flat paragraph block
    Given a raw markdown string "Hello World"
    When the AST parser executes
    Then the root children array must contain exactly 1 node
    And that node must match {"type": "paragraph", "text": "Hello World", "inline_tokens": []}

  Scenario: Accumulate sequential independent paragraph blocks
    Given a raw markdown string "Line One\n\nLine Two"
    When the AST parser executes
    Then the root children array must contain exactly 2 nodes
    And node 0 text must be "Line One"
    And node 1 text must be "Line Two"

  Scenario: Enforce multi-line stateful Blockquote accumulation
    Given a raw markdown string "> This is a\n> blockquote."
    When the AST parser executes
    Then the root children array must contain exactly 1 node
    And that node type must be "blockquote"
    And its combined text content must be "This is a blockquote."

  Scenario: Trigger inline tokenization without breaking the block container
    Given a raw markdown string "Hello **Heavy** World"
    When the AST parser executes
    Then the paragraph node text must remain "Hello Heavy World"
    And its inline_tokens array must contain exactly 1 item
    And that token must match {"type": "strong", "text": "Heavy", "start_idx": 6, "end_idx": 11}

  Scenario: Handle pathologically malformed inline syntax gracefully
    Given a raw markdown string "This **is broken text*"
    When the AST parser executes
    Then the paragraph node inline_tokens array must be empty
    And the raw text must preserve the unmatched asterisks as literal characters
