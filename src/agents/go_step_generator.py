"""
Go Step Definition Generator

Generates Go/Cucumber step definitions from extracted Gherkin scenarios.
This enables cross-language migration: extract Gherkin from Python, implement in Go.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class GoStepGenerator:
    """Generates Go step definitions for Gherkin scenarios."""

    def __init__(self, package_name: str = "steps"):
        """
        Initialize Go step generator.

        Args:
            package_name: Go package name for step definitions
        """
        self.package_name = package_name

    def generate_from_feature_file(self, feature_path: Path, output_dir: Path) -> Path:
        """
        Generate Go step definitions from Gherkin feature file.

        Args:
            feature_path: Path to .feature file
            output_dir: Output directory for Go files

        Returns:
            Path to generated Go file
        """
        logger.info(f"Generating Go steps from: {feature_path}")

        # Read feature file
        with open(feature_path) as f:
            feature_content = f.read()

        # Extract unique steps
        steps = self._extract_steps(feature_content)

        # Generate Go code
        go_code = self._generate_go_code(steps, feature_path.stem)

        # Write to file
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{feature_path.stem}_steps.go"

        with open(output_file, 'w') as f:
            f.write(go_code)

        logger.info(f"Generated Go steps: {output_file}")
        return output_file

    def _extract_steps(self, feature_content: str) -> list[tuple]:
        """
        Extract unique steps from feature file.

        Returns:
            List of (step_type, step_text) tuples
        """
        steps = []
        step_pattern = r'^\s*(Given|When|Then|And|But)\s+(.+)$'

        for line in feature_content.split('\n'):
            match = re.match(step_pattern, line)
            if match:
                step_type = match.group(1).lower()
                step_text = match.group(2).strip()

                # Normalize And/But to their parent type
                if step_type in ['and', 'but']:
                    # Keep last known type
                    step_type = steps[-1][0] if steps else 'given'

                steps.append((step_type, step_text))

        # Remove duplicates while preserving order
        seen = set()
        unique_steps = []
        for step in steps:
            if step not in seen:
                seen.add(step)
                unique_steps.append(step)

        return unique_steps

    def _generate_go_code(self, steps: list[tuple], feature_name: str) -> str:
        """Generate Go code for step definitions."""

        # Start with package and imports
        code = f'''package {self.package_name}

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"github.com/cucumber/godog"
)

// {feature_name.replace('_', ' ').title()}Context holds state for step definitions
type {self._to_camel_case(feature_name)}Context struct {{
	t *testing.T
	// Add fields to store state between steps
	// Example:
	// client      *OAuthClient
	// url         string
	// token       map[string]interface{{}}
	// lastError   error
}}

// New{self._to_camel_case(feature_name)}Context creates a new context
func New{self._to_camel_case(feature_name)}Context(t *testing.T) *{self._to_camel_case(feature_name)}Context {{
	return &{self._to_camel_case(feature_name)}Context{{
		t: t,
	}}
}}

// InitializeScenario registers step definitions
func (ctx *{self._to_camel_case(feature_name)}Context) InitializeScenario(sc *godog.ScenarioContext) {{
'''

        # Add step registrations
        for step_type, step_text in steps:
            func_name = self._step_to_function_name(step_text)
            pattern = self._step_to_regex_pattern(step_text)

            code += f'\tsc.Step(`{pattern}`, ctx.{func_name})\n'

        code += '}\n\n'

        # Add step function implementations
        for step_type, step_text in steps:
            func_name = self._step_to_function_name(step_text)
            params = self._extract_parameters(step_text)

            # Generate function signature
            param_list = ', '.join([f'{pname} string' for pname, _ in params])
            if param_list:
                param_list = ', ' + param_list

            code += f'''// {func_name} implements: {step_type.capitalize()} {step_text}
func (ctx *{self._to_camel_case(feature_name)}Context) {func_name}({param_list}) error {{
	// TODO: Implement this step
	// Step: {step_type.capitalize()} {step_text}
'''

            # Add parameter usage hints
            for pname, pvalue in params:
                code += f'\t// Parameter: {pname} = {pvalue}\n'

            code += '''
	return fmt.Errorf("step not implemented")
}

'''

        return code

    def _step_to_function_name(self, step_text: str) -> str:
        """Convert step text to Go function name."""

        # Remove special characters
        text = re.sub(r'[^\w\s]', '', step_text)

        # Split into words
        words = text.split()

        # Convert to CamelCase
        func_name = ''.join(word.capitalize() for word in words if word)

        # Ensure it starts with lowercase (Go convention for private methods)
        if func_name:
            func_name = func_name[0].lower() + func_name[1:]

        return func_name or 'step'

    def _step_to_regex_pattern(self, step_text: str) -> str:
        """Convert step text to regex pattern."""

        # Escape special regex characters
        pattern = re.escape(step_text)

        # Replace quoted strings with capture groups
        pattern = re.sub(r"'([^']*)'", r"([^']+)", pattern)
        pattern = re.sub(r'"([^"]*)"', r'([^"]+)', pattern)

        # Replace numbers with capture groups
        pattern = re.sub(r'\b\d+\b', r'(\\d+)', pattern)

        return f'^{pattern}$'

    def _extract_parameters(self, step_text: str) -> list[tuple]:
        """Extract parameters from step text."""

        params = []

        # Find quoted strings
        for i, match in enumerate(re.finditer(r"'([^']*)'", step_text)):
            param_name = f'param{i+1}'
            param_value = match.group(1)
            params.append((param_name, param_value))

        # Find numbers if no quoted strings
        if not params:
            for i, match in enumerate(re.finditer(r'\b(\d+)\b', step_text)):
                param_name = f'num{i+1}'
                param_value = match.group(1)
                params.append((param_name, param_value))

        return params

    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to CamelCase."""
        components = snake_str.split('_')
        return ''.join(x.capitalize() for x in components)

    def generate_test_runner(self, output_dir: Path, feature_name: str) -> Path:
        """Generate Go test runner for Cucumber."""

        test_code = f'''package {self.package_name}_test

import (
	"testing"

	"github.com/cucumber/godog"
	"{self.package_name}"
)

func TestFeatures(t *testing.T) {{
	suite := godog.TestSuite{{
		ScenarioInitializer: func(sc *godog.ScenarioContext) {{
			ctx := {self.package_name}.New{self._to_camel_case(feature_name)}Context(t)
			ctx.InitializeScenario(sc)
		}},
		Options: &godog.Options{{
			Format:   "pretty",
			Paths:    []string{{"features"}},
			TestingT: t,
		}},
	}}

	if suite.Run() != 0 {{
		t.Fatal("non-zero status returned, failed to run feature tests")
	}}
}}
'''

        output_file = output_dir / f"{feature_name}_test.go"
        with open(output_file, 'w') as f:
            f.write(test_code)

        logger.info(f"Generated test runner: {output_file}")
        return output_file

    def generate_go_mod(self, output_dir: Path, module_name: str) -> Path:
        """Generate go.mod file."""

        mod_content = f'''module {module_name}

go 1.21

require (
	github.com/cucumber/godog v0.14.0
)
'''

        mod_file = output_dir / "go.mod"
        with open(mod_file, 'w') as f:
            f.write(mod_content)

        logger.info(f"Generated go.mod: {mod_file}")
        return mod_file

    def generate_readme(self, output_dir: Path, feature_name: str) -> Path:
        """Generate README for Go implementation."""

        readme_content = f'''# {feature_name.replace('_', ' ').title()} - Go Implementation

This Go implementation was generated from extracted Gherkin specifications.

## Setup

```bash
# Install dependencies
go mod download

# Run tests
go test -v
```

## Implementation Status

The step definitions have been scaffolded but need implementation.

Each step function in `{feature_name}_steps.go` contains a TODO comment.

## Next Steps

1. Implement the step functions in `{self.package_name}/{feature_name}_steps.go`
2. Add necessary fields to `{self._to_camel_case(feature_name)}Context` struct
3. Run tests: `go test -v`
4. Verify behavior matches original Python implementation

## Cross-Language Verification

Both Python and Go implementations should pass the same Gherkin specifications:

```bash
# Python
cd python_implementation
behave features/{feature_name}.feature

# Go
cd go_implementation
go test -v
```

If both pass, behavior is preserved across languages! 🎉
'''

        readme_file = output_dir / "README.md"
        with open(readme_file, 'w') as f:
            f.write(readme_content)

        logger.info(f"Generated README: {readme_file}")
        return readme_file
