#let ez-table(
  data,
  header-transform: std.strong,
  ..args,
) = {
  let cols = data.at(0).len()
  let headers = data.at(0)
  let row-data = data.slice(1, data.len())

  // table(..data)
  // headers

  table(
    columns: cols,
    table.header(..headers.map(header-transform)),
    ..row-data.flatten(),
    ..args,
  )
}

// #let table(
//   data,
//   /// One of: 'dictionary', 'array', 'records', dictionary, array, auto
//   data-type: auto,
//   /// One of: int, array[str], bool, none
//   header: auto,
//   /// One of: auto, array[int], array[str]
//   use-columns: auto,
//   /// One of: auto, int, str
//   index-column: auto
// ) = {
//   // Determine data type if auto
//   if data-type == auto {
//     if type(data) == dictionary {
//       data-type = "dictionary"
//     } else if type(data) == array {
//       if type(data.at(0)) == dictionary {
//         data-type = "records"
//       } else {
//         data-type = "array"
//       }
//     } else {
//       panic("Unsupported data type for table: " + type(data))
//     }
//   }
//   // Validate data type
//   if data-type == "dictionary" or data-type == dictionary {
//     data-type == "dictionary" // normalize
//     if type(data) != dictionary {
//       panic("Expected dictionary for data-type 'dictionary', got " + type(data))
//     }
//   } else if data-type == "array" or data-type == array {
//     data-type == "array" // normalize
//     if type(data) != array {
//       panic("Expected array for data-type 'array', got " + type(data))
//     }
//   } else if data-type == "records" {
//     if type(data) != array {
//       panic("Expected array for data-type 'records', got " + type(data))
//     }
//     if data.len() > 0 and type(data.at(0)) != dictionary {
//       panic("Expected array of dictionaries for data-type 'records', got " + type(data.at(0)))
//     }
//   } else {
//     panic("Unsupported data-type: " + data-type)
//   }

//   // Transform into interval table representation
//   let __data = ()
//   let __columns = ()
//   let __index = ()
//   let __has-header = false

//   let output = [#data]

//   if data-type == "dictionary" {
//     panic("TODO")
//     for (key, value) in data {
//       output += [#key, #value]
//     }
//   } else if data-type == "array" {
//     panic("TODO")
//   } else if data-type == "records" {
//     if data.len() == 0 {
//       // No records, so data, index, and columns are all empty, which they already are
//     } else {
//       if header == auto or header == true {
//         __has-header = true
//         __columns = data.at(0).keys()
//       } else if type(header) == array {

//       }
//       let first_record = data.at(0)
//       if header
//       __columns = first_record.keys()

//     }
//   }

//   //
//   if header == auto {

//   }


//   output
//   data-type
//   [#__columns]

// }