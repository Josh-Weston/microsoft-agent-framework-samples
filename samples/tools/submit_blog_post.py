import os
from pypdf import PdfReader
from typing import Annotated
from pydantic import Field
from agent_framework import tool


@tool(
    name="submit_blog_post",
    description="Post a blog post with the given title and content."
)
def submit_blog_post(title: Annotated[str, Field(description="The title of the blog post")], content: Annotated[str, Field(description="The blog post content in markdown format")]) -> str:
    """
    Submit a blog post with the given title and content.

    Args:
        title: The title of the blog post
        content: The blog post content in markdown format

    Returns:
        str: A message indicating the result of the submission
    """
    with open("submitted_blog_post.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{content}")
    print(f"Posting blog post: {title}")
    return "Blog post submitted successfully."
