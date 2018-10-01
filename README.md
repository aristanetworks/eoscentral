# eoscentral
Code examples associated with EOS Central articles.

## Instructions on how to add code

Steps to add code from your personal GitHub repository for a new EOS Central article. Assuming the following details:

* GH username: my_user
* GH repo: my_new_repo
* Name of eos central article: my_new_article

First, clone your own repository

```bash
git clone https://github.com/my_user/my_new_repo && my_new_repo 
```

Next, add a new `eosc` remote

```bash
git remote add eosc https://github.com/aristanetworks/eoscentral.git
```

Add all your code to a new "orphan" branch

```bash
git checkout --orphan my_new_article
```

Push your code to the new remote

```bash
git add .; git commit -m "my_new_article"; git push eosc my_new_article
```

If satisfied, remove the `eosc` remote

```bash
git remote remove eos
```