import sqlite3

db = sqlite3.connect("website.db")
cursor = db.cursor()
sql = "select * from website;"
cursor.execute(sql)
result = cursor.fetchall()
for website in result:
    print(website)
print(website[0])

db.close()