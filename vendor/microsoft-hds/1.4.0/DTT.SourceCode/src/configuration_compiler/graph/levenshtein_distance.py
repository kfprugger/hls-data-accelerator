def levenshtein_distance(s1, s2):
    """Return the Levenshtein distance between two strings.
    uses the Wagner-Fischer algorithm"""
    m = len(s1)
    n = len(s2)

    # Create a matrix with (m+1) x (n+1) dimensions
    matrix = [[0] * (n + 1) for _ in range(m + 1)]

    # Initialize the first row and column
    for i in range(m + 1):
        matrix[i][0] = i
    for j in range(n + 1):
        matrix[0][j] = j

    # Fill in the rest of the matrix
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                cost = 0
            else:
                cost = 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,  # Deletion
                matrix[i][j - 1] + 1,  # Insertion
                matrix[i - 1][j - 1] + cost,
            )  # Substitution

    # The bottom-right cell of the matrix contains the Levenshtein distance
    return matrix[m][n]
