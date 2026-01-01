# Insurance-Policy-RAG
# Insurance Policy RAG Assistant

This project demonstrates how Retrieval-Augmented Generation (RAG) can be used to help interpret complex insurance policy documents by providing clear, document-grounded answers with citations.

## Motivation

Understanding insurance coverage often requires navigating long policy PDFs or contacting the insurer directly. While the information exists, it is not always easy notice to locate or interpret.

This project was created to reduce that friction by building a system that:
- Retrieves relevant sections from an insurance policy
- Generates clear, natural-language answers
- Grounds every response in the source document
- Explicitly refuses to answer questions that are not supported by the policy text

## What This Project Does

- Uses a single insurance policy document as the **source of truth**
- Splits the document into semantically meaningful chunks
- Stores embeddings in a vector database
- Retrieves relevant policy sections for each user question
- Generates answers using a large language model
- Provides citations (page numbers / sections) where possible

## What This Project Does NOT Do

- It does not provide legal or financial advice
- It does not generalize across insurers or policy types
- It does not interpret or extrapolate beyond the policy text

## Architecture Overview

1. PDF ingestion and text extraction  
2. Chunking with overlap and metadata  
3. Embedding generation (Gemini embeddings)  
4. Vector storage (ChromaDB)  
5. Similarity-based retrieval  
6. Constrained answer generation with guardrails  

## Source of Truth

The system is designed to work with **one specific insurance policy document**.
Answers are valid only for users covered by the same policy.

For privacy reasons, the policy PDF is not included in this repository.

## How to Use

1. Place your insurance policy PDF in:

