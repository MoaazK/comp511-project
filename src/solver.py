import copy
import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.utils.data import DataLoader
from tqdm import tqdm
from typing import Union

from utils.Metrics import Metrics
from models import UNet, AttentionUNet, TransformerUNet
from utils.config import ACCURACY, AUPRC, AUROC_, DICE_SCORE, F1_SCORE, JACCARD_INDEX, PRECISION, RECALL, SPECIFICITY

class Solver:
    def __init__(
        self,
        model: Union[UNet, AttentionUNet, TransformerUNet],
        epochs: int,
        device: torch.device,
        train_loader: DataLoader,
        val_loader: DataLoader,
        criterion: nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler: object = None) -> None:

        self.epochs = epochs
        self.device = device
        self.model = model
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.criterion = criterion
        self.optimizer = optimizer
        self.scheduler = scheduler

        self.train_metrics = Metrics(self.device, 2)
        self.val_metrics = Metrics(self.device, 2)
        self.train_loss_history = []
        self.val_loss_history = []
        self.train_loss_batch = []

        self.best_model = copy.deepcopy(self.model)
        self.best_dice_score = 0.0

    def fit(self):
        for epoch in range(1, self.epochs + 1):
            print(f'Epoch {epoch}/{self.epochs}')

            self.train_metrics.reset()
            self.val_metrics.reset()

            t1, t2 = self.train(self.model, self.criterion, self.optimizer, self.device, self.train_loader, self.train_metrics)
            self.train_loss_batch.extend(t1)
            self.train_loss_history.append(t2)

            self.val_loss_history.append(self.evaluate(self.model, self.criterion, self.device, self.val_loader, self.val_metrics))

            train_agg_metrics = self.train_metrics.compute()
            val_agg_metrics = self.val_metrics.compute()

            if not self.scheduler:
                self.scheduler.step(self.val_loss_history[-1])

            if val_agg_metrics[DICE_SCORE] > self.best_dice_score:
                self.best_dice_score = val_agg_metrics[DICE_SCORE]
                self.best_model = copy.deepcopy(self.model)

            print(f'Training   - Accuracy: {train_agg_metrics[ACCURACY]:.4f} | Dice: {train_agg_metrics[DICE_SCORE]:.4f} | IoU: {train_agg_metrics[JACCARD_INDEX]:.4f} | Loss: {t2:.4f}')
            print(f'Validation - Accuracy: {val_agg_metrics[ACCURACY]:.4f} | Dice: {val_agg_metrics[DICE_SCORE]:.4f} | IoU: {val_agg_metrics[JACCARD_INDEX]:.4f} | Loss: {self.train_loss_batch[-1]:.4f}')
            print()

    def train(
        self,
        model: Union[UNet, AttentionUNet, TransformerUNet],
        criterion: nn.Module,
        optimizer: torch.optim.Optimizer,
        device: torch.device,
        dataloader: DataLoader,
        metrics: Metrics):

        loss_sum = 0
        loss_total = 0
        avg_sum = 0
        train_loss = []
        model.train()

        pbar = tqdm(enumerate(dataloader), total=len(dataloader), desc='Training  ')
        for batch_idx, (X, Y) in pbar:
            optimizer.zero_grad()
            X, Y = Variable(X.to(device=device)), Y.to(device=device)
            batch_size = X.size(0)

            logits: torch.Tensor = model(X)
            loss = criterion(logits, Y)
            loss.backward()
            optimizer.step()

            loss = loss.detach()
            l = loss.item()
            avg_sum += l
            loss_sum += l * batch_size
            loss_total += batch_size
            train_loss.append(avg_sum / (batch_idx + 1))

            metric_dict = metrics.update(logits, Y)
            pbar.set_postfix(
                Loss=f'{train_loss[-1]:.4f}',
                Accuracy=f'{metric_dict[ACCURACY]:.4f}',
                Dice=f'{metric_dict[DICE_SCORE]:.4f}',
                IoU=f'{metric_dict[JACCARD_INDEX]:.4f}'
            )

        return train_loss, loss_sum / loss_total

    @staticmethod
    @torch.inference_mode()
    def evaluate(
        self,
        model: Union[UNet, AttentionUNet, TransformerUNet],
        criterion: nn.Module,
        device: torch.device,
        dataloader: DataLoader,
        metrics: Metrics,
        decsription='Validation'):

        total = 0
        all_loss = 0
        avg_sum = 0
        model.eval()

        pbar = tqdm(enumerate(dataloader), total=len(dataloader), desc=decsription)
        for batch_idx, (X, Y) in pbar:
            X, Y = Variable(X.to(device=device)), Y.to(device=device)
            batch_size = X.size(0)

            logits: torch.Tensor = model(X)
            loss = criterion(logits, Y)

            loss = loss.detach()
            l = loss.item()
            avg_sum += l
            all_loss += l * batch_size
            total += batch_size

            metric_dict = metrics.update(logits, Y)
            pbar.set_postfix(
                Loss=f'{avg_sum / (batch_idx + 1):.4f}',
                Accuracy=f'{metric_dict[ACCURACY]:.4f}',
                Dice=f'{metric_dict[DICE_SCORE]:.4f}',
                IoU=f'{metric_dict[JACCARD_INDEX]:.4f}'
            )
        
        return all_loss / total
