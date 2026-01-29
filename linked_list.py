class Node:
    def __init__(self, data):
        self.data = data
        self.next = None
class LinkedList:
    def __init__(self):
        self.head = None    
        self.tail = None

    def insert_at_beginning(self, data):
        new_node = Node(data)
        if self.head is None:
            self.head = new_node
            self.tail = new_node
        else:
            new_node.next = self.head
            self.head = new_node
        return True
    
    def insert_at_end(self, data):
        new_node = Node(data)
        if self.head is None:
            self.head = new_node
            self.tail = new_node
        else:
            self.tail.next = new_node
            self.tail = new_node
        return True
    
    def print_linked_list(self):
        current_node = self.head
        while current_node:
            print(current_node.data)
            current_node = current_node.next
    
    def insert_at_position(self, data, position):
        new_node = Node(data)
        if position == 0:
            return self.insert_at_beginning(data)
        current_node = self.head
        current_position = 0
        while current_node and current_position < position - 1:
            current_node = current_node.next
            current_position += 1 
        if current_node is None:
            return self.insert_at_end(data)
        new_node.next = current_node.next
        current_node.next = new_node
        if new_node.next is None:
            self.tail = new_node
        return True

    def remove_at_beginning(self):
        if self.head is None:
            return True
        self.head = self.head.next
        if self.head is None:
            self.tail = None
        return True

    def remove_at_end(self):
        if self.head is None:
            return True
        if self.head.next is None:
            self.head = None
            self.tail = None
            return True
        current_node = self.head
        while current_node.next and current_node.next.next:
            current_node = current_node.next
        current_node.next = None
        self.tail = current_node
        return True

    def remove_at_position(self, position):
        if self.head is None:
            return True
        if position == 0:
            return self.remove_at_beginning()
        current_node = self.head
        current_position = 0
        while current_node.next and current_position < position - 1:
            current_node = current_node.next
            current_position += 1
        if current_node.next is None:
            return True
        current_node.next = current_node.next.next
        if current_node.next is None:
            self.tail = current_node
        return True            
