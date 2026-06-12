"""
Data Loader Module
Handles loading and preprocessing of documents for the RAG chatbot
"""

import os
from typing import List, Optional
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    DirectoryLoader,
    CSVLoader,
    UnstructuredMarkdownLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


class DataLoader:
    """
    Load and process various document types for the chatbot
    """
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize the data loader
        
        Args:
            chunk_size: Size of text chunks for splitting
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
    
    def load_text_file(self, file_path: str) -> List[Document]:
        """
        Load a single text file
        
        Args:
            file_path: Path to the text file
            
        Returns:
            List of Document objects
        """
        try:
            loader = TextLoader(file_path, encoding='utf-8')
            documents = loader.load()
            return self.text_splitter.split_documents(documents)
        except Exception as e:
            print(f"Error loading text file {file_path}: {str(e)}")
            return []
    
    def load_pdf_file(self, file_path: str) -> List[Document]:
        """
        Load a single PDF file
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            List of Document objects
        """
        try:
            loader = PyPDFLoader(file_path)
            documents = loader.load()
            return self.text_splitter.split_documents(documents)
        except Exception as e:
            print(f"Error loading PDF file {file_path}: {str(e)}")
            return []
    
    def load_csv_file(self, file_path: str) -> List[Document]:
        """
        Load a single CSV file
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            List of Document objects
        """
        try:
            loader = CSVLoader(file_path)
            documents = loader.load()
            return self.text_splitter.split_documents(documents)
        except Exception as e:
            print(f"Error loading CSV file {file_path}: {str(e)}")
            return []
    
    def load_markdown_file(self, file_path: str) -> List[Document]:
        """
        Load a single Markdown file
        
        Args:
            file_path: Path to the Markdown file
            
        Returns:
            List of Document objects
        """
        try:
            loader = UnstructuredMarkdownLoader(file_path)
            documents = loader.load()
            return self.text_splitter.split_documents(documents)
        except Exception as e:
            print(f"Error loading Markdown file {file_path}: {str(e)}")
            return []
    
    def load_directory(self, directory_path: str, glob_pattern: str = "**/*.txt") -> List[Document]:
        """
        Load all files from a directory matching a pattern
        
        Args:
            directory_path: Path to the directory
            glob_pattern: Pattern to match files (e.g., "**/*.txt", "**/*.pdf")
            
        Returns:
            List of Document objects
        """
        try:
            # Determine loader class based on pattern
            if "*.pdf" in glob_pattern:
                loader = DirectoryLoader(
                    directory_path,
                    glob=glob_pattern,
                    loader_cls=PyPDFLoader
                )
            elif "*.csv" in glob_pattern:
                loader = DirectoryLoader(
                    directory_path,
                    glob=glob_pattern,
                    loader_cls=CSVLoader
                )
            elif "*.md" in glob_pattern:
                loader = DirectoryLoader(
                    directory_path,
                    glob=glob_pattern,
                    loader_cls=UnstructuredMarkdownLoader
                )
            else:
                loader = DirectoryLoader(
                    directory_path,
                    glob=glob_pattern,
                    loader_cls=TextLoader
                )
            
            documents = loader.load()
            return self.text_splitter.split_documents(documents)
        except Exception as e:
            print(f"Error loading directory {directory_path}: {str(e)}")
            return []
    
    def load_from_string(self, text: str, metadata: Optional[dict] = None) -> List[Document]:
        """
        Load documents from a string
        
        Args:
            text: Text content to load
            metadata: Optional metadata for the document
            
        Returns:
            List of Document objects
        """
        try:
            document = Document(page_content=text, metadata=metadata or {})
            return self.text_splitter.split_documents([document])
        except Exception as e:
            print(f"Error loading from string: {str(e)}")
            return []
    
    def load_multiple_files(self, file_paths: List[str]) -> List[Document]:
        """
        Load multiple files of different types
        
        Args:
            file_paths: List of file paths to load
            
        Returns:
            Combined list of Document objects
        """
        all_documents = []
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue
            
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext == '.pdf':
                documents = self.load_pdf_file(file_path)
            elif ext == '.csv':
                documents = self.load_csv_file(file_path)
            elif ext in ['.md', '.markdown']:
                documents = self.load_markdown_file(file_path)
            elif ext == '.txt':
                documents = self.load_text_file(file_path)
            else:
                print(f"Unsupported file type: {ext}")
                continue
            
            all_documents.extend(documents)
        
        print(f"Loaded {len(all_documents)} document chunks from {len(file_paths)} files")
        return all_documents


# Example usage
if __name__ == "__main__":
    # Initialize the data loader
    loader = DataLoader(chunk_size=1000, chunk_overlap=200)
    
    # Example 1: Load a single text file
    # documents = loader.load_text_file("data/sample.txt")
    
    # Example 2: Load all text files from a directory
    # documents = loader.load_directory("data/", glob_pattern="**/*.txt")
    
    # Example 3: Load multiple files of different types
    # file_paths = ["data/doc1.txt", "data/doc2.pdf", "data/doc3.csv"]
    # documents = loader.load_multiple_files(file_paths)
    
    # Example 4: Load from string
    sample_text = """
    This is sample text about CUI Campus.
    The university has multiple departments and facilities.
    Students can access various resources on campus.
    """
    documents = loader.load_from_string(
        sample_text,
        metadata={"source": "sample", "type": "campus_info"}
    )
    
    print(f"Number of document chunks: {len(documents)}")
    if documents:
        print(f"First chunk preview: {documents[0].page_content[:200]}...")
