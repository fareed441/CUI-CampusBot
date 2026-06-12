"""
Fuzzy course matching using RapidFuzz.
Maps natural language queries like "AI" to canonical course codes.
"""
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    
from .models import Course, Offering


@dataclass
class FuzzyMatch:
    """Result of a fuzzy match"""
    course_code: str
    course_name: str
    score: float
    matched_term: str
    
    def to_dict(self) -> Dict:
        return {
            "course_code": self.course_code,
            "course_name": self.course_name,
            "score": self.score,
            "matched_term": self.matched_term,
        }


class CourseMatcher:
    """
    Fuzzy matcher for course names and codes.
    """
    
    # Common aliases for courses (can be extended)
    DEFAULT_ALIASES = {
        "CSC301": ["AI", "Artificial Intelligence", "A.I."],
        "CSC302": ["ML", "Machine Learning", "M.L."],
        "CSC101": ["ITC", "ICT", "Intro to Computing", "Introduction to Computing"],
        "CSC102": ["PF", "Programming Fundamentals", "Programming"],
        "CSC201": ["OOP", "Object Oriented Programming", "Object-Oriented"],
        "CSC202": ["DSA", "Data Structures", "DS", "Algorithms"],
        "CSC303": ["DB", "Database", "Database Systems", "DBMS"],
        "CSC304": ["OS", "Operating Systems", "Operating System"],
        "CSC305": ["CN", "Networking", "Computer Networks"],
        "CSC306": ["SE", "Software Engineering", "Soft Eng"],
        "MTH101": ["Calculus", "Cal", "Math", "Calculus 1", "Calculus I"],
        "MTH201": ["LA", "Linear Algebra", "Algebra"],
        "MTH202": ["Probability", "Prob", "Stats", "Statistics"],
        "PHY101": ["Physics", "Applied Physics", "Phy"],
        "ENG101": ["English", "Eng", "Communication Skills"],
    }
    
    def __init__(self):
        self.courses: Dict[str, Course] = {}
        self.search_index: Dict[str, str] = {}  # term -> course_code
        
    def register_course(self, course: Course):
        """Register a course for fuzzy matching."""
        self.courses[course.course_code] = course
        
        # Add to search index
        code_lower = course.course_code.lower()
        name_lower = course.course_name.lower()
        
        self.search_index[code_lower] = course.course_code
        self.search_index[name_lower] = course.course_code
        
        # Add default aliases if available
        if course.course_code in self.DEFAULT_ALIASES:
            for alias in self.DEFAULT_ALIASES[course.course_code]:
                self.search_index[alias.lower()] = course.course_code
        
        # Add custom aliases from course
        for alias in course.aliases:
            self.search_index[alias.lower()] = course.course_code
    
    def register_courses_from_offerings(self, offerings: List[Offering]):
        """Extract and register courses from offerings list."""
        seen = set()
        for offering in offerings:
            if offering.course.course_code not in seen:
                self.register_course(offering.course)
                seen.add(offering.course.course_code)
    
    def exact_match(self, query: str) -> Optional[str]:
        """Try exact match first (case-insensitive)."""
        query_lower = query.lower().strip()
        return self.search_index.get(query_lower)
    
    def fuzzy_match(
        self, 
        query: str, 
        threshold: float = 60.0,
        limit: int = 5
    ) -> List[FuzzyMatch]:
        """
        Fuzzy match a query to courses.
        
        Args:
            query: User query like "AI" or "artificial intel"
            threshold: Minimum score to include (0-100)
            limit: Maximum results to return
            
        Returns:
            List of FuzzyMatch results, sorted by score descending
        """
        query = query.strip()
        if not query:
            return []
        
        # Try exact match first
        exact = self.exact_match(query)
        if exact and exact in self.courses:
            course = self.courses[exact]
            return [FuzzyMatch(
                course_code=exact,
                course_name=course.course_name,
                score=100.0,
                matched_term=query
            )]
        
        if not RAPIDFUZZ_AVAILABLE:
            # Fallback: simple substring matching
            return self._simple_match(query, threshold, limit)
        
        # Use RapidFuzz for fuzzy matching
        results = []
        search_terms = list(self.search_index.keys())
        
        matches = process.extract(
            query.lower(),
            search_terms,
            scorer=fuzz.WRatio,
            limit=limit * 2  # Get more candidates for deduplication
        )
        
        seen_codes = set()
        for matched_term, score, _ in matches:
            if score < threshold:
                continue
            
            course_code = self.search_index[matched_term]
            if course_code in seen_codes:
                continue
            seen_codes.add(course_code)
            
            if course_code in self.courses:
                course = self.courses[course_code]
                results.append(FuzzyMatch(
                    course_code=course_code,
                    course_name=course.course_name,
                    score=score,
                    matched_term=matched_term
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    def _simple_match(
        self, 
        query: str, 
        threshold: float,
        limit: int
    ) -> List[FuzzyMatch]:
        """Simple substring matching fallback when RapidFuzz is unavailable."""
        query_lower = query.lower()
        results = []
        
        seen_codes = set()
        for term, course_code in self.search_index.items():
            if course_code in seen_codes:
                continue
            
            # Simple substring score
            if query_lower in term or term in query_lower:
                score = 80.0 if query_lower == term else 60.0
            else:
                # Check if all query chars appear in order
                score = self._subsequence_score(query_lower, term)
            
            if score >= threshold:
                seen_codes.add(course_code)
                if course_code in self.courses:
                    course = self.courses[course_code]
                    results.append(FuzzyMatch(
                        course_code=course_code,
                        course_name=course.course_name,
                        score=score,
                        matched_term=term
                    ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    def _subsequence_score(self, query: str, target: str) -> float:
        """Simple subsequence matching score."""
        if not query:
            return 0.0
        
        target_idx = 0
        matches = 0
        
        for char in query:
            while target_idx < len(target):
                if target[target_idx] == char:
                    matches += 1
                    target_idx += 1
                    break
                target_idx += 1
        
        if matches == len(query):
            return 50.0 + (50.0 * matches / len(target))
        return 0.0
    
    def get_course(self, course_code: str) -> Optional[Course]:
        """Get course by code."""
        return self.courses.get(course_code)
    
    def search(self, query: str) -> List[FuzzyMatch]:
        """
        Main search interface - returns best fuzzy matches.
        """
        return self.fuzzy_match(query, threshold=50.0, limit=5)


# Global matcher instance
_global_matcher: Optional[CourseMatcher] = None


def get_course_matcher() -> CourseMatcher:
    """Get or create global course matcher."""
    global _global_matcher
    if _global_matcher is None:
        _global_matcher = CourseMatcher()
    return _global_matcher


def match_course_query(query: str) -> List[FuzzyMatch]:
    """
    Convenience function to match a query.
    """
    return get_course_matcher().search(query)
