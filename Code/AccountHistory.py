import glob 
import pandas as pd
import numpy as np
from numpy.typing import NDArray
from typing import Any, List
import camelot
import os

class Transaction():
    """Implements a financial transaction as a dictionary-like object"""
    def __init__(self, date, accountID, amount, balance, description, currency="CAD"):
        self.date = date
        self.accountID = accountID
        self.amount = amount
        self.balance = balance
        self.description = description
        self.currency = currency

    @property
    def dict(self):
        return {"date":self.date,"accountID": self.accountID,"amount":self.amount,"balance":self.balance,"description":self.description,"currency":self.currency}

class Loader():
    data_filename = "Data/FinancesData.csv"
    update_filename = "Data/FinancesUpdate.csv"
    accountId_filename= "Data/AccountIDs.csv"

    @staticmethod
    def upload():
        """
        Checks if any new files must be added and adds them to the datafile
        """
        updates = pd.read_csv(Loader.update_filename)        
        accountIDs = pd.read_csv(Loader.accountId_filename).to_dict(orient = "list")
        data = pd.read_csv(Loader.data_filename).to_dict(orient = "list")

        newfiles = [filename for filename in glob.glob(f"Statements/*") if Loader.check(filename, updates)]
        updates = updates.to_dict(orient="list")

        for filename in newfiles:
            if "MasterCard Statement" in filename:
                '''RBC Statement'''
                accountIDs, statements = Loader.RBCtoTransactions(filename, accountIDs)
            elif "monthly-statement-transactions" in filename:
                '''Wealthsimple Statement'''
                accountIDs, statements = Loader.WealthsimpletoTransactions(filename,accountIDs)
            else:
                raise(NotImplementedError(f"{filename} is not a supported statement type"))
            
            for statement in statements:
                for key in data.keys():
                    data[key].append(statement.dict[key])
            updates["filename"].append(filename)
        #TODO: Add new accounts when files are added     
        pd.DataFrame(accountIDs).to_csv(Loader.accountId_filename, index = False)   
        pd.DataFrame(data).to_csv(Loader.data_filename, index = False)
        pd.DataFrame(updates).to_csv(Loader.update_filename, index = False)

    @staticmethod  
    def check(filename: str, updates)-> bool:
        '''Checks if the file exists and needs uploading to the datafile'''
        if(not os.path.exists(filename)):
            raise(FileNotFoundError(f"{filename} does not exist"))
        elif(filename in updates["filename"].values):
            return False
        else:
            return True

    @staticmethod
    def RBCtoTransactions(filename, accountIDs)->List[Transaction]:
        #Cassandra's code for reading RBC PDF statements
        tables = camelot.read_pdf(
            filename,
            flavor="stream"   # RBC statements work best with stream
        )
        df_raw = pd.concat([t.df for t in tables], ignore_index=True)
        df = df_raw.copy()
        df.columns = ["transaction_date", "posting_date", "description", "amount", "extra"]
        df = df.fillna("")
        import re
        mask = (
            df["transaction_date"].str.match(
                r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{1,2}",
                na=False
            )
            & df["amount"].str.contains(r"\$", na=False)
        )
        df_tx = df[mask].copy()
        df_tx["amount"] = (
            df_tx["amount"]
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .astype(float)
        )
        accountNumber = int(filename.split(" ")[1][-4:])
        if(accountNumber not in map(lambda x: int(x) if not np.isnan(x) else '', accountIDs["Number"])):
            accountIDs = Loader.newAccount(accountIDs,"RBC","",accountNumber)
        accountId = accountIDs["AccountID"][accountIDs["Number"].index(accountNumber)]
        balance = None #TODO: Extract balance from statement
        currency = "CAD" #Default currency
        year = int(re.search(r"\d{4}", filename.split(" ")[2]).group(0))
        transactions = []
        for entry in df_tx.itertuples():
            month, date = entry.transaction_date.split(" ")
            month = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"].index(month) + 1
            day = "{}-{}-{}".format(year,month,date)
            transactions.append(Transaction(day, accountId, entry.amount, balance, entry.description, currency))
        return accountIDs,transactions

    @staticmethod
    def WealthsimpletoTransactions(filename, accountIDs)->List[Transaction]:
        statements = np.array(pd.read_csv(filename))
        transactions = []
        for entry in statements:
            accountName = filename.split("\\")[-1].split("-")[0]
            if(accountName not in accountIDs["AccountName"]):
                accountIDs = Loader.newAccount(accountIDs,"Wealthsimple",accountName,"")
            accountID = accountIDs["AccountID"][accountIDs["AccountName"].index(accountName)]
            transaction = Transaction(entry[0], accountID, entry[3], entry[4], entry[2], entry[5])
            transactions.append(transaction)
        return accountIDs,transactions

    def newAccount(accountIDs,bank,name,number):
        '''Determines a new ID and as much other information available'''
        newID = min([i for i in range(0,len(accountIDs["AccountID"])+1) if i not in accountIDs["AccountID"]]) #Finds the first empty spot
        account = {"AccountID": newID, "AccountName": name, "Number": number, "Type" : "", "Owner": "", "Bank": bank}
        for key in account.keys():
            accountIDs[key].append(account[key])
        return accountIDs
    
class updateAccount():

    def update(id:int,accountName:str,number:int,type:str,owner:str,bank:str):
        accountIDs = pd.read_csv(Loader.accountId_filename)
        #TODO:
