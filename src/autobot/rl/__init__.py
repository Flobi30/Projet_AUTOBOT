class RLModule:
    def __init__(self, name):
        self.name = name

    def greet(self):
        # Construit exactement la chaîne attendue par le test
        return f"Welcome to the {self.name} Reinforcement Learning Module"
