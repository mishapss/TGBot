from telegram.ext.filters import BaseFilter
from states import user_states

class StateFilter(BaseFilter):
    def __init__(self, state):
        self.state = state
        
    def filter(self, message):
        return user_states.get(message.from_user.id) == self.state
        
    @property
    def data_filter(self):
        return True
  