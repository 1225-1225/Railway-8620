from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableWithMessageHistory

import config_data
from agent.chat_history import ChatHistory
from agent.vector_store import VectorStoreService


def get_session_history(session_id):
    return ChatHistory(session_id)

class LLMService:
    def __init__(self):
        self.retriever = VectorStoreService()
        self.model = ChatTongyi(model=config_data.chat_model_name)
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system","你是一位知晓中国铁路和机车方方面面知识的专家，"
                          "请根据提供的资料专业的详细的回答用户的问题，参考资料：{context}"),
                ("system","并且我提供和用户的历史对话如下"),
                MessagesPlaceholder("history"),
                ("user","请回答用户的问题：{input}")
            ]
        )

    def get_model(self):
        return self.model

    def get_chain(self):
        retriever = self.retriever.get_retriever()
        model = self.model
        prompt = self.prompt

        base_chain = (
                RunnablePassthrough.assign(    #此方法可以执行下面的lambda表达式为字典添加新的键值对
                    context=lambda x: retriever.invoke(x["input"])    #此处添加了context键值对
                )
                | prompt
                | model
        )
        # 包装为带历史的链
        chain_with_history = RunnableWithMessageHistory(
            base_chain,
            get_session_history=get_session_history,    #根据session_history获取历史的函数
            input_messages_key="input",
            history_messages_key="history"
        )
        return chain_with_history

if __name__ == '__main__':
    chat = LLMService()
    res = chat.get_chain().invoke({"input":"前进型蒸汽机车在其中的地位"}, config_data.session_config)
    print(res.content)
