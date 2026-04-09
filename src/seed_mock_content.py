"""
Seed rich learning material content into the existing DSA course 
for testing Bloom's Taxonomy Generation.
"""
import sqlite3
import json
import os

# Path to the SQLite database
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "db.sqlite")

def make_paragraph(text):
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": []
    }

def make_heading(text, level=2):
    return {
        "type": "heading",
        "props": {"level": level},
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": []
    }

def make_code(text, language="python"):
    return {
        "type": "codeBlock",
        "props": {"language": language},
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": []
    }

def make_bullet(text):
    return {
        "type": "bulletListItem",
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": []
    }

# ============================================================
# Learning Material 1: Introduction to Trees
# ============================================================
trees_intro_blocks = [
    make_heading("Introduction to Trees", 1),
    make_paragraph(
        "A tree is a hierarchical data structure consisting of nodes connected by edges. "
        "Unlike linear data structures such as arrays, linked lists, stacks, and queues, "
        "trees are non-linear and allow for efficient data organization and retrieval."
    ),
    make_heading("Key Terminology"),
    make_bullet("Root: The topmost node in a tree. It has no parent."),
    make_bullet("Node: A fundamental unit of a tree containing data and references to child nodes."),
    make_bullet("Edge: The connection between a parent node and a child node."),
    make_bullet("Leaf: A node with no children (also called a terminal node)."),
    make_bullet("Height: The length of the longest path from the root to a leaf node."),
    make_bullet("Depth: The length of the path from the root to a given node."),
    make_bullet("Subtree: A tree formed by a node and all its descendants."),
    make_bullet("Degree: The number of children a node has."),
    make_heading("Properties of Trees"),
    make_paragraph(
        "A tree with N nodes always has exactly N-1 edges. There is exactly one path "
        "between any two nodes in a tree. A tree is a connected, acyclic graph. "
        "The height of a tree with a single node is 0."
    ),
    make_heading("Types of Trees"),
    make_paragraph(
        "1. Binary Tree: Each node has at most two children (left and right). "
        "Binary trees are the most commonly studied tree structure."
    ),
    make_paragraph(
        "2. Binary Search Tree (BST): A binary tree where the left child contains values "
        "less than the parent, and the right child contains values greater than the parent. "
        "This property makes searching efficient with O(log n) average-case time complexity."
    ),
    make_paragraph(
        "3. AVL Tree: A self-balancing BST where the difference in heights of left and right "
        "subtrees (balance factor) of any node is at most 1. Named after inventors Adelson-Velsky and Landis."
    ),
    make_paragraph(
        "4. Red-Black Tree: A self-balancing BST with an extra bit of storage per node for color "
        "(red or black). Used in many real-world applications like Java's TreeMap and C++ STL map."
    ),
    make_paragraph(
        "5. B-Tree: A self-balancing tree data structure that maintains sorted data and allows "
        "searches, insertions, and deletions in O(log n) time. Widely used in databases and file systems."
    ),
    make_heading("Real-World Applications of Trees"),
    make_bullet("File systems: Directory structures are organized as trees."),
    make_bullet("HTML DOM: Web page elements are organized in a tree structure."),
    make_bullet("Database indexing: B-Trees and B+ Trees are used for efficient data retrieval."),
    make_bullet("Network routing: Spanning trees are used in network protocol algorithms."),
    make_bullet("Compilers: Abstract Syntax Trees (AST) represent the structure of source code."),
    make_bullet("AI/ML: Decision trees are used for classification and regression."),
]

# ============================================================
# Learning Material 2: Binary Search Tree Operations
# ============================================================
bst_operations_blocks = [
    make_heading("Binary Search Tree (BST) Operations", 1),
    make_paragraph(
        "A Binary Search Tree is a fundamental data structure that enables efficient "
        "searching, insertion, and deletion operations. The key property of a BST is: "
        "for any node, all values in its left subtree are smaller, and all values in "
        "its right subtree are larger."
    ),
    make_heading("BST Node Structure"),
    make_code(
        "class TreeNode:\n"
        "    def __init__(self, val):\n"
        "        self.val = val\n"
        "        self.left = None\n"
        "        self.right = None",
        "python"
    ),
    make_heading("1. Search Operation"),
    make_paragraph(
        "Searching in a BST starts at the root. If the target value equals the current node's value, "
        "we've found it. If the target is less, we search the left subtree. If greater, we search the right subtree. "
        "Time complexity: O(h) where h is the height of the tree. For a balanced BST, h = O(log n)."
    ),
    make_code(
        "def search(root, target):\n"
        "    if root is None or root.val == target:\n"
        "        return root\n"
        "    if target < root.val:\n"
        "        return search(root.left, target)\n"
        "    return search(root.right, target)",
        "python"
    ),
    make_heading("2. Insertion Operation"),
    make_paragraph(
        "Insertion in a BST always creates a new leaf node. We traverse the tree comparing values "
        "until we find the appropriate null position. The BST property is maintained because we "
        "always insert in the correct position relative to existing nodes. "
        "Time complexity: O(h)."
    ),
    make_code(
        "def insert(root, val):\n"
        "    if root is None:\n"
        "        return TreeNode(val)\n"
        "    if val < root.val:\n"
        "        root.left = insert(root.left, val)\n"
        "    elif val > root.val:\n"
        "        root.right = insert(root.right, val)\n"
        "    return root",
        "python"
    ),
    make_heading("3. Deletion Operation"),
    make_paragraph(
        "Deletion in a BST has three cases: "
        "(a) Node to delete is a leaf: Simply remove it. "
        "(b) Node has one child: Replace the node with its child. "
        "(c) Node has two children: Find the in-order successor (smallest value in the right subtree), "
        "replace the node's value with the successor's value, and delete the successor."
    ),
    make_code(
        "def delete(root, key):\n"
        "    if root is None:\n"
        "        return root\n"
        "    if key < root.val:\n"
        "        root.left = delete(root.left, key)\n"
        "    elif key > root.val:\n"
        "        root.right = delete(root.right, key)\n"
        "    else:\n"
        "        # Node with one child or no child\n"
        "        if root.left is None:\n"
        "            return root.right\n"
        "        elif root.right is None:\n"
        "            return root.left\n"
        "        # Node with two children\n"
        "        successor = find_min(root.right)\n"
        "        root.val = successor.val\n"
        "        root.right = delete(root.right, successor.val)\n"
        "    return root\n\n"
        "def find_min(node):\n"
        "    current = node\n"
        "    while current.left is not None:\n"
        "        current = current.left\n"
        "    return current",
        "python"
    ),
    make_heading("4. Tree Traversals"),
    make_paragraph(
        "Tree traversal is the process of visiting each node in the tree exactly once. "
        "There are several traversal methods:"
    ),
    make_paragraph(
        "In-order Traversal (Left, Root, Right): Visits nodes in ascending order for a BST. "
        "This is the most common traversal for BSTs because it produces a sorted sequence."
    ),
    make_code(
        "def inorder(root):\n"
        "    if root:\n"
        "        inorder(root.left)\n"
        "        print(root.val, end=' ')\n"
        "        inorder(root.right)",
        "python"
    ),
    make_paragraph(
        "Pre-order Traversal (Root, Left, Right): Useful for creating a copy of the tree "
        "or getting a prefix expression of an expression tree."
    ),
    make_paragraph(
        "Post-order Traversal (Left, Right, Root): Useful for deleting the tree "
        "or getting a postfix expression of an expression tree."
    ),
    make_paragraph(
        "Level-order Traversal (BFS): Visits nodes level by level using a queue. "
        "Time complexity: O(n). Space complexity: O(w) where w is the maximum width of the tree."
    ),
    make_code(
        "from collections import deque\n\n"
        "def level_order(root):\n"
        "    if not root:\n"
        "        return []\n"
        "    result = []\n"
        "    queue = deque([root])\n"
        "    while queue:\n"
        "        node = queue.popleft()\n"
        "        result.append(node.val)\n"
        "        if node.left:\n"
        "            queue.append(node.left)\n"
        "        if node.right:\n"
        "            queue.append(node.right)\n"
        "    return result",
        "python"
    ),
    make_heading("Time Complexity Summary"),
    make_paragraph(
        "| Operation | Average Case | Worst Case (skewed) |\n"
        "|-----------|-------------|--------------------|\n"
        "| Search    | O(log n)    | O(n)               |\n"
        "| Insert    | O(log n)    | O(n)               |\n"
        "| Delete    | O(log n)    | O(n)               |\n"
        "| Traversal | O(n)        | O(n)               |"
    ),
    make_paragraph(
        "The worst case occurs when the BST becomes degenerate (essentially a linked list), "
        "which happens when elements are inserted in sorted order. Self-balancing trees like "
        "AVL trees and Red-Black trees solve this problem by ensuring O(log n) height."
    ),
    make_heading("Common BST Problems"),
    make_bullet("Validate BST: Check if a given binary tree is a valid BST."),
    make_bullet("Lowest Common Ancestor: Find the LCA of two nodes in a BST."),
    make_bullet("Kth Smallest Element: Find the kth smallest element in a BST."),
    make_bullet("Convert Sorted Array to BST: Create a height-balanced BST from a sorted array."),
    make_bullet("Serialize and Deserialize BST: Convert a BST to a string and back."),
]

def main():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Update task 1 (Intro) with rich Trees content
    cursor.execute(
        "UPDATE tasks SET blocks = ?, title = ? WHERE id = ?",
        (json.dumps(trees_intro_blocks), "Introduction to Trees", 1)
    )
    print(f"✅ Updated task 1: 'Introduction to Trees' ({len(trees_intro_blocks)} blocks)")

    # Update task 2 (Intro 2) with BST Operations content
    cursor.execute(
        "UPDATE tasks SET blocks = ?, title = ? WHERE id = ?",
        (json.dumps(bst_operations_blocks), "BST Operations & Traversals", 2)
    )
    print(f"✅ Updated task 2: 'BST Operations & Traversals' ({len(bst_operations_blocks)} blocks)")

    conn.commit()
    conn.close()
    print("\n🎉 Mock content seeded successfully! You can now generate Bloom's questions from the 'Trees' module.")

if __name__ == "__main__":
    main()
