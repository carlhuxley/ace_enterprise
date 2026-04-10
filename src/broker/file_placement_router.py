class ProjectAwareAgent:
    def route_file(self, filename: str, feature_description: str) -> str:
        """
        Routes a file to the appropriate project directory based on feature keywords.
        
        Args:
            filename: Name of the file to be placed
            feature_description: Description of the feature containing keywords
            
        Returns:
            Full path string for the file placement
        """
        feature_description = feature_description.lower()
        
        if "broker" in feature_description or "routing" in feature_description:
            return f"src/broker/{filename}"
        elif "agent" in feature_description:
            return f"src/agents/{filename}"
        elif "storage" in feature_description or "repository" in feature_description:
            return f"src/storage/{filename}"
        return f"src/{filename}"