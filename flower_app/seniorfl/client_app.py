
import torch

from flwr.clientapp import ClientApp
from flwr.common import (
    ArrayRecord,
    MetricRecord,
    RecordDict,
    Message,
    Context,
)

from seniorfl.task import MLP, load_client, train_local

app = ClientApp()


@app.train()
def train(msg: Message, context: Context):
    partition_id = int(context.node_config["partition-id"])
    client_id = partition_id + 1

    round_num = int(
        msg.content["config"]["server-round"]
    )

    batch_size = int(context.run_config["batch-size"])
    local_epochs = int(context.run_config["local-epochs"])
    lr = float(context.run_config["learning-rate"])

    torch.set_num_threads(1)

    model = MLP()
    model.load_state_dict(
        msg.content["arrays"].to_torch_state_dict()
    )

    loader, num_examples = load_client(
        client_id, batch_size, round_num
    )

    train_loss = train_local(
        model, loader, local_epochs, lr
    )

    print(
        f"Client {client_id} | Round {round_num} | "
        f"Records: {num_examples} | Loss: {train_loss:.4f}",
        flush=True
    )

    return Message(
        content=RecordDict({
            "arrays": ArrayRecord(model.state_dict()),
            "metrics": MetricRecord({
                "train_loss": float(train_loss),
                "num-examples": int(num_examples),
            }),
        }),
        reply_to=msg,
    )
