"""Parsing the matrixes in a PDF file"""
from logging import getLogger
from typing import Any, Optional
from pikepdf import Matrix, Operator, Page, parse_content_stream

logger = getLogger(__file__)
OPERATOR_CM = Operator('cm')  # "Concatenate Matrix": Changes the CTM (Current Transformation Matrix)
OPERATOR_DO = Operator('Do')  # "Draw Object": 
OPERATOR_STACK = Operator('q')  # Stores the CTM to a stack
OPERATOR_POP = Operator('Q')  # Restores the previous CTM

class MatrixStack:
    """Tracks the CTM (current transformation matrix) in a PDF content stream
    
    The CTM starts as the identity matrix and can be changed via the 'cm' (concatenate matrix) operator
    --> CTM = CTM x CM (with CTM and CM being 3x3 matrixes)

    Furthermore can the CTM be stored to the stack via the 'q' operator.
    This save the CTM and subsequent 'cm' operators change a copy of that CTM
    --> 'q 1 0 0 1 0 0 cm'
    --> Copy CTM onto the stack and change the copy via 'cm'

    With the 'Q' operator the current CTM is replaced with the previous one from the stack

    Error handling:
    1. Popping from an empty stack results in CTM being set to the identity matrix
    2. Multiplying with invalid operands sets the CTM to invalid
    3. Multiplying an invalid CTM with a valid CM results in an invalid CTM
    4. Stacking an invalid CTM results in a copy of that invalid CTM onto the stack
    --> All operations with an invalid CTM result in an invalid CTM
    --> The CTM is valid again when all invalid CTMs are popped off the stack
    """
    def __init__(self) -> None:
        self._identity_matrix = Matrix(1, 0, 0, 1, 0, 0)
        self._stack: list[Optional[Matrix]] = [self._identity_matrix]
    
    def stack(self):
        """Copying the current CTM onto the stack"""
        self._stack.append(self._stack[-1])
    
    def pop(self):
        """Removing the current CTM from the stack"""
        assert len(self._stack) >= 1, "can't be empty"
        if len(self._stack) == 1:
            self._stack = [self._identity_matrix]
        else:
            self._stack.pop()
    
    def multiply(self, matrix: Matrix):
        """Multiplies the CTM with `matrix`"""
        if self._stack[-1] is None:
            return
        else:
            self._stack[-1] = self._stack[-1] @ matrix

    def invalidate_current_transformation_matrix(self):
        """Registers the occurence of an invalid CM. See `# Error handling` for further informations"""
        self._stack[-1] = None

    @property
    def ctm(self) -> Matrix | None:
        """Returns the current transformation matrix or `None` if it's invalid"""
        return self._stack[-1]

def get_objects_with_ctm(page: Page) -> list[tuple[str, Matrix]]:
    """Determines the current transformation matrix (CTM) for each drawn object
    
    Filters objects with an invalid CTM 
    """
    objects_with_ctm: list[tuple[str, Matrix]] = []  # Stores the matrixes and the corresponding objects
    matrix_stack = MatrixStack()
    for operands, operator in parse_content_stream(page):
        if operator == OPERATOR_STACK:
            matrix_stack.stack()
        
        elif operator == OPERATOR_POP:
            matrix_stack.pop()
        
        elif operator == OPERATOR_CM:
            try:
                matrix_stack.multiply(Matrix(*operands))
            except TypeError:
                logger.debug(f"malformed operands for `cm` operator: {operands}")
                matrix_stack.invalidate_current_transformation_matrix()
        
        elif operator == OPERATOR_DO:
            name = str(operands[0])  # Name of the image (or other object)
            if matrix_stack.ctm is not None:
                objects_with_ctm.append((name, matrix_stack.ctm))  # Explicit copying the CTM
            else:
                logger.debug(f"skipping `Do` operator due to invalid CTM for object: {name}")

    return objects_with_ctm