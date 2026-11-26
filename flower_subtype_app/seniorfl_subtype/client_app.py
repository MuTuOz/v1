import torch
from flwr.clientapp import ClientApp
from flwr.common import ArrayRecord, Context, Message, MetricRecord, RecordDict

from .task import DEFAULTS, SubtypeMLP, project_root, train_local

app = ClientApp()


@app.train()
def train(msg: Message, context: Context):
    config = {**DEFAULTS, **context.run_config, **dict(msg.content["config"])}
    client_id = int(context.node_config["partition-id"]) + 1
    if client_id not in range(1, 6):
        raise ValueError("Exactly five client partitions are required")
    round_num = int(config["server-round"])
    torch.set_num_threads(1)
    model = SubtypeMLP()
    model.load_state_dict(msg.content["arrays"].to_torch_state_dict())
    loss, count = train_local(model, project_root(config), client_id, round_num, config)
    print(f"Client {client_id} round {round_num}: n={count}, loss={loss:.6f}", flush=True)
    return Message(RecordDict({"arrays": ArrayRecord(model.state_dict()),
                              "metrics": MetricRecord({"train_loss": loss,
                                                       "num-examples": count,
                                                       "client-id": client_id})}), reply_to=msg)
