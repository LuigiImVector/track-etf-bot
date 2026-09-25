CREATE TABLE IF NOT EXISTS user_account (
    id SERIAL PRIMARY KEY,
    uuid_account VARCHAR (16) UNIQUE NOT NULL,
    username VARCHAR (64) NOT NULL,
    insert_date TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ticker (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR (32) NOT NULL,
    user_account_id integer,
    CONSTRAINT fk_user_account
      FOREIGN KEY(user_account_id)
        REFERENCES user_account(id)
);