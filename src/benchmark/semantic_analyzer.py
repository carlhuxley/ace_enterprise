class SemanticCodeAnalyzer:
    def __init__(self):
        self.sql_analyzer = SQLAnalyzer()
        self.eval_analyzer = EvalAnalyzer()
        self.exec_analyzer = ExecAnalyzer()
        self.secret_analyzer = SecretAnalyzer()

    def analyze(self, code):
        issues = []
        
        # SQL analysis
        sql_result = self.sql_analyzer.detect(code)
        if sql_result.get("details") and "sql_concatenation" in sql_result["details"]:
            issues.append({
                "type": "sql_concatenation",
                "severity": sql_result["severity"],
                "line": sql_result["line"],
                "column": sql_result["column"],
                "context": sql_result["context"]
            })
            
        # Eval analysis
        eval_result = self.eval_analyzer.detect(code)
        if eval_result.get("details") and "eval_usage" in eval_result["details"]:
            issues.append({
                "type": "eval_usage",
                "severity": eval_result["severity"],
                "line": eval_result["line"],
                "column": eval_result["column"],
                "context": eval_result["context"]
            })
            
        # Exec analysis
        exec_result = self.exec_analyzer.detect(code)
        if exec_result.get("details") and "exec_usage" in exec_result["details"]:
            issues.append({
                "type": "exec_usage",
                "severity": exec_result["severity"],
                "line": exec_result["line"],
                "column": exec_result["column"],
                "context": exec_result["context"]
            })
            
        # Secret analysis
        secret_result = self.secret_analyzer.detect(code)
        if secret_result.get("details") and "hardcoded_secret" in secret_result["details"]:
            issues.append({
                "type": "hardcoded_secret",
                "severity": secret_result["severity"],
                "line": secret_result["line"],
                "column": secret_result["column"],
                "context": secret_result["context"]
            })
            
        return issues


class SQLAnalyzer:
    def detect(self, code):
        lines = code.split('\n')
        for i, line in enumerate(lines):
            if '+' in line and any(sql_keyword in line.upper() for sql_keyword in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                # Find the SQL query part
                quote_start = line.find("'") if "'" in line else line.find('"')
                if quote_start == -1:
                    continue
                    
                # Get the SQL query context
                query_part = line[quote_start:]
                before_plus = query_part.split('+')[0]
                after_plus = query_part.split('+')[-1]
                context = f"{before_plus} + {after_plus}".strip()
                
                return {
                    "severity": "critical",
                    "details": {
                        "sql_concatenation": line.strip()
                    },
                    "line": i + 1,
                    "column": line.index('+') + 1,
                    "context": context
                }
        return {"severity": "low", "details": {}}


class EvalAnalyzer:
    def detect(self, code):
        lines = code.split('\n')
        for i, line in enumerate(lines):
            if 'eval(' in line:
                context_start = line.index('eval(') + 5
                context_end = line.rfind(')')
                context = line[context_start:context_end].strip('"\'') if context_end > context_start else ""
                
                return {
                    "severity": "critical",
                    "details": {
                        "eval_usage": line.strip()
                    },
                    "line": i + 1,
                    "column": line.index('eval(') + 1,
                    "context": context
                }
        return {"severity": "low", "details": {}}


class ExecAnalyzer:
    def detect(self, code):
        lines = code.split('\n')
        for i, line in enumerate(lines):
            if 'exec(' in line:
                context_start = line.index('exec(') + 5
                context_end = line.rfind(')')
                context = line[context_start:context_end].strip('"\'') if context_end > context_start else ""
                
                return {
                    "severity": "critical",
                    "details": {
                        "exec_usage": line.strip()
                    },
                    "line": i + 1,
                    "column": line.index('exec(') + 1,
                    "context": context
                }
        return {"severity": "low", "details": {}}


class SecretAnalyzer:
    def detect(self, code):
        lines = code.split('\n')
        for i, line in enumerate(lines):
            # Check for various assignment patterns with quotes
            patterns = [
                (' = "', '"'),  # double quotes with spaces
                (' = \'', '\''),  # single quotes with spaces
                ('="', '"'),    # double quotes no space
                ('=\'', '\'')   # single quotes no space
            ]
            
            for op_pattern, quote_char in patterns:
                if op_pattern in line:
                    parts = line.split(op_pattern, 1)
                    if len(parts) > 1:
                        secret_part = parts[1].split(quote_char)[0]
                        if len(secret_part) > 8 and any(c.isdigit() for c in secret_part) and any(c.isalpha() for c in secret_part):
                            return {
                                "severity": "high",
                                "details": {
                                    "hardcoded_secret": line.strip()
                                },
                                "line": i + 1,
                                "column": line.index(op_pattern) + 2,
                                "context": secret_part  # Return the exact secret value
                            }
        return {"severity": "low", "details": {}}