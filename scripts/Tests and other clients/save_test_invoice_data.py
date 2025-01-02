import json
import os

# Test invoice data
invoice_data = [
    {
        "id": "6198e755ca52bf072243b2d6",
        "field_1350": "<span class=\"6137eb81819e32001e69f34a\">Dixie Nespor 275</span>",
        "field_1385": "<span class=\"5a68befa8f300363dafb8b2e\">The Mapleton Andover</span>",
        "field_1369": "<span class=\"6137ec80ff7bc2001fb8c2cb\">Dixie Nespor, Agmnt Date: 09/07/2021 Base Care: $3900, Personal Care: $1650</span>",
        "field_1351": "01/01/2022",
        "field_1418": "Andover1001094",
        "field_2090": "$5,500.00",
        "field_2540": "Dixie Nespor"
    },
    {
        "id": "61c075e6ce6574072181430b",
        "field_1350": "<span class=\"6137eb81819e32001e69f34a\">Dixie Nespor 275</span>",
        "field_1385": "<span class=\"5a68befa8f300363dafb8b2e\">The Mapleton Andover</span>",
        "field_1369": "<span class=\"6137ec80ff7bc2001fb8c2cb\">Dixie Nespor, Agmnt Date: 09/07/2021 Base Care: $3900, Personal Care: $1650</span>",
        "field_1351": "02/01/2022",
        "field_1418": "Andover1001113",
        "field_2090": "$5,500.00",
        "field_2540": "Dixie Nespor"
    },
    {
        "id": "62ba27e112f7c70021140a1d",
        "field_1350": "<span class=\"629656e5d18d45001ea35111\">Jackson Newcom 287</span>",
        "field_1385": "<span class=\"5a68befa8f300363dafb8b2e\">The Mapleton Andover</span>",
        "field_1369": "<span class=\"62965e4b0c66ee001e24abf6\">Jackson Newcom, Agmnt Date: 05/31/2022 Base Care: $3900, Personal Care: $1650</span>",
        "field_1351": "06/27/2022",
        "field_1418": "Andover1001211",
        "field_2090": "$5,500.00",
        "field_2540": "Jackson Newcom"
    },
    {
        "id": "custom_1",
        "field_1350": "<span class=\"custom\">Kurt Elliott 413</span>",
        "field_1385": "<span class=\"5a68befa8f300363dafb8b2e\">The Mapleton Andover</span>",
        "field_1369": "<span class=\"custom\">Kurt Elliott, Base Care: $3900, Personal Care: $1650</span>",
        "field_1351": "10/01/2024",
        "field_1418": "Andover1002816",
        "field_2090": "$5,490.00",
        "field_2540": "Kurt Elliott"
    }
]

def main():
    # Get the test folder path
    folder_path = input("Enter the path to your test folder: ")
    
    # Save invoice data
    output_file = os.path.join(folder_path, "invoice_data.json")
    with open(output_file, 'w') as f:
        json.dump(invoice_data, f, indent=2)
    print(f"Saved invoice data to: {output_file}")

if __name__ == "__main__":
    main()
